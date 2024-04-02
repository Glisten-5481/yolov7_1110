# yolov7_1110

**模型选择**： 此工具支持三种模型，用户可以通过设置以下参数选择要使用的模型：

--weights: 指定 all_model 的权重文件路径，默认为 'runs/train/exp/weights/best.pt'。

--bottle: 使用 bottle_model，默认为 True。

--bottle-weights: 指定 bottle_model 的权重文件路径，默认为'runs/train/bottle/weights/best.pt'。

--lighter: 使用 lighter_model，默认为 True。

--lighter-weights: 指定 lighter_model 的权重文件路径，默认为'runs/train/lighter/weights/best.pt'。


**阈值设置**： 用户可以通过以下参数调整指定类别对象识别的阈值：

--[cls]-conf-thres: 对象置信度阈值，默认为 0.25。

--[cls]-iou-thres: 非极大值抑制 (NMS) 的 IOU 阈值，默认为 0.45。

 检测类别: "gun", "knife", "scissors", "tongs", "wrench", "lighter", "bottle"


**运行**：
python detect.py --bottle True --lighter True --gun-conf-thres 0.25 --gun-c-iou-thres 0.45
