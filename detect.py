import argparse
import time
from pathlib import Path

import cv2
import torch
import torch.backends.cudnn as cudnn
from numpy import random

from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_synchronized, TracedModel


def detect(save_img=False):
    source, view_img, save_txt, imgsz, trace = opt.source, opt.view_img, opt.save_txt, opt.img_size, not opt.no_trace

    weights, bottle, lighter = opt.weights, opt.bottle, opt.lighter

    save_img = not opt.nosave and not source.endswith('.txt')  # save inference images
    webcam = source.isnumeric() or source.endswith('.txt') or source.lower().startswith(
        ('rtsp://', 'rtmp://', 'http://', 'https://'))

    # Directories
    save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(opt.device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size

    # if trace:
    #     model = TracedModel(model, device, opt.img_size)

    if half:
        model.half()  # to FP16
    
    if bottle:
        bottle_weights = opt.bottle_weights
        bottle_model = attempt_load(bottle_weights, map_location=device)
        if half:
            bottle_model.half()  # to FP16
    
    if lighter:
        lighter_weights = opt.lighter_weights
        lighter_model = attempt_load( lighter_weights, map_location=device)
        if half:
            lighter_model.half()  # to FP16

    # # Second-stage classifier
    # classify = False
    # if classify:
    #     modelc = load_classifier(name='resnet101', n=2)  # initialize
    #     modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    vid_path, vid_writer = None, None
    if webcam:
        view_img = check_imshow()
        cudnn.benchmark = True  # set True to speed up constant image size inference
        dataset = LoadStreams(source, img_size=imgsz, stride=stride)
    else:
        dataset = LoadImages(source, img_size=imgsz, stride=stride)

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    old_img_w = old_img_h = imgsz
    old_img_b = 1

    t0 = time.time()
    for path, img, im0s, vid_cap in dataset:
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Warmup
        if device.type != 'cpu' and (old_img_b != img.shape[0] or old_img_h != img.shape[2] or old_img_w != img.shape[3]):
            old_img_b = img.shape[0]
            old_img_h = img.shape[2]
            old_img_w = img.shape[3]
            for i in range(3):
                model(img, augment=opt.augment)[0]

        # Inference
        t1 = time_synchronized()
        with torch.no_grad():   # Calculating gradients would cause a GPU memory leak
            pred = model(img, augment=opt.augment)[0]

        if bottle:
            with torch.no_grad():
                bottle_pred = bottle_model(img, augment=opt.augment)[0]
            pred = torch.cat((pred, bottle_pred), dim = 0)
        
        if lighter:
            with torch.no_grad():
                lighter_pred = lighter_model(img, augment=opt.augment)[0]
            pred = torch.cat((pred, lighter_pred), dim = 0)

        t2 = time_synchronized()

        # Apply NMS
        # names: ["gun", "knife", "scissors", "tongs", "wrench", "lighter", "bottle"]
        # print(opt.gun_conf_thres)
        gun_det = non_max_suppression(pred, opt.gun_conf_thres, opt.gun_iou_thres, classes=0, agnostic=opt.agnostic_nms)
        knife_det = non_max_suppression(pred, opt.knife_conf_thres, opt.knife_iou_thres, classes=1, agnostic=opt.agnostic_nms)
        scissors_det = non_max_suppression(pred, opt.scissors_conf_thres, opt.scissors_iou_thres, classes=2, agnostic=opt.agnostic_nms)
        tongs_det = non_max_suppression(pred, opt.tongs_conf_thres, opt.tongs_iou_thres, classes=3, agnostic=opt.agnostic_nms)
        wrench_det = non_max_suppression(pred, opt.wrench_conf_thres, opt.wrench_iou_thres, classes=4, agnostic=opt.agnostic_nms)
        lighter_det = non_max_suppression(pred, opt.lighter_conf_thres, opt.lighter_iou_thres, classes=5, agnostic=opt.agnostic_nms)
        bottle_det = non_max_suppression(pred, opt.bottle_conf_thres, opt.bottle_iou_thres, classes=6, agnostic=opt.agnostic_nms)        
        
        dets = [gun_det, knife_det, scissors_det, tongs_det, wrench_det, lighter_det, bottle_det]

        # 初始化拼接后的张量列表
        concatenated_dets = []

        # 假设每个检测列表都有相同数量的张量（在这个例子中是3）
        for i in range(3):
            # 选取每个列表中的第i个张量，如果它不为空，则添加到临时列表中
            tensors_to_concat = [det[i] for det in dets if det[i].numel() > 0]

            # 如果有非空张量，则拼接它们；否则，创建一个空张量
            if tensors_to_concat:
                concatenated_det = torch.cat(tensors_to_concat, dim=0)
            else:
            # 假设每个张量的形状是 [N, 6]，创建一个形状为 [0, 6] 的空张量
                concatenated_det = torch.empty((0, 6), device='cuda:0')
                # concatenated_det = torch.empty((0, 6))
    
            concatenated_dets.append(concatenated_det)
        
        
        # pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
        pred = concatenated_dets
        
        t3 = time_synchronized()


        # Apply Classifier
        # if classify:
        #     pred = apply_classifier(pred, modelc, img, im0s)

        # Process detections
        for i, det in enumerate(pred):  # detections per image
            if webcam:  # batch_size >= 1
                p, s, im0, frame = path[i], '%g: ' % i, im0s[i].copy(), dataset.count
            else:
                p, s, im0, frame = path, '', im0s, getattr(dataset, 'frame', 0)

            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # img.jpg
            txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # Write results
                for *xyxy, conf, cls in reversed(det):
                    if save_txt:  # Write to file
                        xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                        line = (cls, *xywh, conf) if opt.save_conf else (cls, *xywh)  # label format
                        with open(txt_path + '.txt', 'a') as f:
                            f.write(('%g ' * len(line)).rstrip() % line + '\n')

                    if save_img or view_img:  # Add bbox to image
                        label = f'{names[int(cls)]} {conf:.2f}'
                        plot_one_box(xyxy, im0, label=label, color=colors[int(cls)], line_thickness=1)

            # Print time (inference + NMS)
            print(f'{s}Done. ({(1E3 * (t2 - t1)):.1f}ms) Inference, ({(1E3 * (t3 - t2)):.1f}ms) NMS')

            # Stream results
            if view_img:
                cv2.imshow(str(p), im0)
                cv2.waitKey(1)  # 1 millisecond

            # Save results (image with detections)
            if save_img:
                if dataset.mode == 'image':
                    cv2.imwrite(save_path, im0)
                    # print(f" The image with the result is saved in: {save_path}")
                else:  # 'video' or 'stream'
                    if vid_path != save_path:  # new video
                        vid_path = save_path
                        if isinstance(vid_writer, cv2.VideoWriter):
                            vid_writer.release()  # release previous video writer
                        if vid_cap:  # video
                            fps = vid_cap.get(cv2.CAP_PROP_FPS)
                            w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        else:  # stream
                            fps, w, h = 30, im0.shape[1], im0.shape[0]
                            save_path += '.mp4'
                        vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                    vid_writer.write(im0)

    if save_txt or save_img:
        s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ''
        #print(f"Results saved to {save_dir}{s}")

    print(f'Done. ({time.time() - t0:.3f}s)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--weights', nargs='+', type=str, default='runs/train/exp/weights/best.pt', help='all_model.pt path(s)')

    parser.add_argument('--bottle', type=bool, default=True, help='use bottle_model')
    parser.add_argument('--bottle-weights', nargs='+', type=str, default='runs/train/bottle/weights/best.pt', help='bottle_model.pt path(s)')

    parser.add_argument('--lighter', type=bool, default=True, help='use lighter_model')
    parser.add_argument('--lighter-weights', nargs='+', type=str, default='runs/train/lighter/weights/best.pt', help='lighter_model.pt path(s)')

     # names: ["gun", "knife", "scissors", "tongs", "wrench", "lighter", "bottle"]
    parser.add_argument('--gun-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--gun-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--knife-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--knife-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--scissors-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--scissors-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--tongs-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--tongs-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--wrench-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--wrench-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--lighter-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--lighter-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--bottle-conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--bottle-iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    
    parser.add_argument('--source', type=str, default='/data/qfl/security-check-main/test', help='source')  # file/folder, 0 for webcam
    parser.add_argument('--img-size', type=int, default=640, help='inference size (pixels)')
    parser.add_argument('--device', default='2', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--no-trace', action='store_true', help='don`t trace model')
    opt = parser.parse_args()
    print(opt)
    #check_requirements(exclude=('pycocotools', 'thop'))

    with torch.no_grad():
        if opt.update:  # update all models (to fix SourceChangeWarning)
            for opt.weights in ['yolov7.pt']:
                detect()
                strip_optimizer(opt.weights)
        else:
            detect()