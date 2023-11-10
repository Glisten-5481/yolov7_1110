import torch
import torch.nn as nn
import torch.nn.functional as F



class FocalLoss(nn.Module):
    def __init__(self, gamma=2, alpha=0.25):
        super(FocalLoss, self).__init__()
        self.gamma = gamma
        self.alpha = alpha

    def forward(self, logits, targets):
        BCE_loss = F.binary_cross_entropy_with_logits(logits, targets, reduction='none')
        p_t = torch.exp(-BCE_loss)
        focal_loss = (1 - p_t) ** self.gamma * BCE_loss

        alpha_factor = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        focal_loss = alpha_factor * focal_loss

        return focal_loss.mean()
