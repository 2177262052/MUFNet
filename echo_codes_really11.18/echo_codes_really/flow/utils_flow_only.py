import numpy as np
import sys
import os
import cv2
import torch.nn.functional as F
import torch
import torch.nn as nn
import re
import matplotlib.pyplot as plt
from dice_loss import dice_coeff
import pytorch_ssim

TAG_FLOAT = 202021.25
# testing vim, and git push


def readflo(file):
    assert type(file) is str, "file is not str %r" % str(file)
    assert os.path.isfile(file) is True, "file does not exist %r" % str(file)
    assert file[-4:] == '.flo', "file ending is not .flo %r" % file[-4:]
    f = open(file, 'rb')
    flo_number = np.fromfile(f, np.float32, count=1)[0]
    assert flo_number == TAG_FLOAT, 'Flow number %r incorrect. Invalid .flo file' % flo_number
    w = np.fromfile(f, np.int32, count=1)
    h = np.fromfile(f, np.int32, count=1)
    data = np.fromfile(f, np.float32, count=2 * w[0] * h[0])
    flow = np.resize(data, (int(h[0]), int(w[0]), 2))
    f.close()

    return flow


def readPFM(file):
    file = open(file, 'rb')

    color = None
    width = None
    height = None
    scale = None
    endian = None

    header = file.readline().rstrip()
    if header.decode("ascii") == 'PF':
        color = True
    elif header.decode("ascii") == 'Pf':
        color = False
    else:
        raise Exception('Not a PFM file.')

    dim_match = re.match(r'^(\d+)\s(\d+)\s$', file.readline().decode("ascii"))
    if dim_match:
        width, height = list(map(int, dim_match.groups()))
    else:
        raise Exception('Malformed PFM header.')

    scale = float(file.readline().decode("ascii").rstrip())
    if scale < 0: # little-endian
        endian = '<'
        scale = -scale
    else:
        endian = '>' # big-endian

    data = np.fromfile(file, endian + 'f')
    shape = (height, width, 3) if color else (height, width)

    data = np.reshape(data, shape)
    data = np.flipud(data)
    return data[:, :, :2]


def makeColorwheel():

    RY = 15
    YG = 6
    GC = 4
    CB = 11
    BM = 13
    MR = 6

    ncols = RY + YG + GC + CB + BM + MR

    colorwheel = np.zeros([ncols, 3])  # r g b

    col = 0
    # RY
    colorwheel[0:RY, 0] = 255
    colorwheel[0:RY, 1] = np.floor(255 * np.arange(0, RY, 1) / RY)
    col += RY

    # YG
    colorwheel[col:YG + col, 0] = 255 - np.floor(255 * np.arange(0, YG, 1) / YG)
    colorwheel[col:YG + col, 1] = 255
    col += YG

    # GC
    colorwheel[col:GC + col, 1] = 255
    colorwheel[col:GC + col, 2] = np.floor(255 * np.arange(0, GC, 1) / GC)
    col += GC

    # CB
    colorwheel[col:CB + col, 1] = 255 - np.floor(255 * np.arange(0, CB, 1) / CB)
    colorwheel[col:CB + col, 2] = 255
    col += CB

    # BM
    colorwheel[col:BM + col, 2] = 255
    colorwheel[col:BM + col, 0] = np.floor(255 * np.arange(0, BM, 1) / BM)
    col += BM

    # MR
    colorwheel[col:MR + col, 2] = 255 - np.floor(255 * np.arange(0, MR, 1) / MR)
    colorwheel[col:MR + col, 0] = 255
    return colorwheel


def computeColor(u, v):
    colorwheel = makeColorwheel()
    nan_u = np.isnan(u)
    nan_v = np.isnan(v)
    nan_u = np.where(nan_u)
    nan_v = np.where(nan_v)

    u[nan_u] = 0
    u[nan_v] = 0
    v[nan_u] = 0
    v[nan_v] = 0

    ncols = colorwheel.shape[0]
    radius = np.sqrt(u ** 2 + v ** 2)
    a = np.arctan2(-v, -u) / np.pi
    fk = (a + 1) / 2 * (ncols - 1)  # -1~1 maped to 1~ncols
    k0 = fk.astype(np.uint8)  # 1, 2, ..., ncols
    k1 = k0 + 1
    k1[k1 == ncols] = 0
    f = fk - k0

    img = np.empty([k1.shape[0], k1.shape[1], 3])
    ncolors = colorwheel.shape[1]
    for i in range(ncolors):
        tmp = colorwheel[:, i]
        col0 = tmp[k0] / 255
        col1 = tmp[k1] / 255
        col = (1 - f) * col0 + f * col1
        idx = radius <= 1
        col[idx] = 1 - radius[idx] * (1 - col[idx])  # increase saturation with radius
        col[~idx] *= 0.75  # out of range
        img[:, :, 2 - i] = np.floor(255 * col).astype(np.uint8)

    #img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img.astype(np.uint8)


def computeImg(flow, verbose=False, savePath=None):
    eps = sys.float_info.epsilon
    UNKNOWN_FLOW_THRESH = 1e9
    UNKNOWN_FLOW = 1e10
    if flow.shape[0] == 2:
        u = flow[0, :, :]
        v = flow[1, :, :]
    else:
        u = flow[:, :, 0]
        v = flow[:, :, 1]

    maxu = -999
    maxv = -999

    minu = 999
    minv = 999

    maxrad = -1
    # fix unknown flow
    greater_u = np.where(u > UNKNOWN_FLOW_THRESH)
    greater_v = np.where(v > UNKNOWN_FLOW_THRESH)
    u[greater_u] = 0
    u[greater_v] = 0
    v[greater_u] = 0
    v[greater_v] = 0

    maxu = max([maxu, np.amax(u)])
    minu = min([minu, np.amin(u)])

    maxv = max([maxv, np.amax(v)])
    minv = min([minv, np.amin(v)])
    rad = np.sqrt(np.multiply(u, u) + np.multiply(v, v))
    maxrad = max([maxrad, np.amax(rad)])

    u = u / (maxrad + eps)
    v = v / (maxrad + eps)
    img = computeColor(u, v)
    if savePath is not None:
        cv2.imwrite(savePath, img)
    if verbose:
        cv2.imshow('image', img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def computerArrows(flow, step=16, verbose=False, savePath=None, img=None):
    h, w = flow.shape[:2]
    y, x = np.mgrid[step / 2:h:step, step / 2:w:step].reshape(2, -1).astype(int)
    fx, fy = flow[y, x].T
    lines = np.vstack([x, y, x + fx, y + fy]).T.reshape(-1, 2, 2)
    lines = np.int32(lines + 0.5)
    if img is None:
        vis = np.ones((h, w)).astype('uint8')*255
    else:
        vis = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    cv2.polylines(vis, lines, 0, (0, 255, 0))
    for (x2, y2), (x1, y1) in lines:
        cv2.circle(vis, (x1, y1), 1, (0, 255, 0), -1)

    if savePath is not None:
        cv2.imwrite(savePath, vis)
    if verbose:
        cv2.imshow('arrowsViz', vis)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    return vis


def disp_function(pred_flo, true_flo):
    height, width = true_flo.shape[1:]
    # print(true_flo.dim())
    pred_flo = F.interpolate(pred_flo, (height, width), mode='bilinear', align_corners=False)
    pred_flo = computeImg(pred_flo[0].cpu().numpy())
    # print(pred_flo.shape)
    if true_flo.shape[0] == 2:
        true_flo = computeImg(true_flo.cpu().numpy())
        image1, image2 = np.expand_dims(pred_flo, axis=0), np.expand_dims(true_flo, axis=0)
        return np.concatenate((image1, image2), axis=0)
    else:
        true_flo = true_flo[:3]
        true_flo = true_flo.transpose(0, 2)
        true_flo = true_flo.transpose(0, 1)
        image1, image2 = np.expand_dims(pred_flo, axis=0), np.expand_dims(true_flo.cpu().numpy(), axis=0)
        # print(image1.size(), image2.size())
        return np.concatenate((image1, image2), axis=0)


def EPE(flow_pred, flow_true, real=False):

    if real:
        batch_size, _, h, w = flow_true.shape
        flow_pred = F.interpolate(flow_pred, (h, w), mode='bilinear', align_corners=False)
    else:
        batch_size, _, h, w = flow_pred.shape
        flow_true = F.interpolate(flow_true, (h, w), mode='area')
    return torch.norm(flow_pred - flow_true, 2, 1).mean()


def EPE_all(flows_pred, flow_true, weights=(0.005, 0.01, 0.02, 0.08, 0.32)):

    if len(flows_pred) < 5:
        weights = [0.005]*len(flows_pred)
    loss = 0

    for i in range(len(weights)):
        loss += weights[i] * EPE(flows_pred[i], flow_true, real=False)

    return loss


def AAE(flow_pred, flow_true):
    batch_size, _, h, w = flow_true.shape
    flow_pred = F.interpolate(flow_pred, (h, w), mode='bilinear', align_corners=False)
    numerator = torch.sum(torch.mul(flow_pred, flow_pred), dim=1) + 1
    denominator = torch.sqrt(torch.sum(flow_pred ** 2, dim=1) + 1) * torch.sqrt(torch.sum(flow_true ** 2, dim=1) + 1)
    result = torch.clamp(torch.div(numerator, denominator), min=-1.0, max=1.0)

    return torch.acos(result).mean()


def evaluate(flow_pred, flow_true):

    epe = EPE(flow_pred, flow_true, real=True)
    aae = AAE(flow_pred, flow_true)
    return epe, aae


def charbonnier(x, alpha=0.25, epsilon=1.e-9):
    return torch.pow(torch.pow(x, 2) + epsilon**2, alpha)


def smoothness_loss(flow):
    b, c, h, w = flow.size()
    v_translated = torch.cat((flow[:, :, 1:, :], torch.zeros(b, c, 1, w, device=flow.device)), dim=-2)
    h_translated = torch.cat((flow[:, :, :, 1:], torch.zeros(b, c, h, 1, device=flow.device)), dim=-1)
    s_loss = charbonnier(flow - v_translated) + charbonnier(flow - h_translated)
    s_loss = torch.sum(s_loss, dim=1) / 2

    return torch.sum(s_loss)/b


# def photometric_loss(warped, frame1):
#     h, w = warped.shape[2:]
#     frame1 = F.interpolate(frame1, (h, w), mode='bilinear', align_corners=False)
#     p_loss = F.mse_loss(warped, frame1)
#     # print('''ploss''',p_loss.size())
#     # p_loss = torch.sum(p_loss, dim=1)/3
#     # print('''ploss''', torch.sum(p_loss))
#     return torch.sum(p_loss)/frame1.size(0)

def DSSIM(x,y):

    avgpooling2d = nn.AvgPool2d(3, stride = 1, padding = [1,1])
    mu_x = avgpooling2d(x)
    mu_y = avgpooling2d(y)
    sigma_x = avgpooling2d(x ** 2) - mu_x ** 2
    sigma_y = avgpooling2d(y ** 2) - mu_y ** 2
    sigma_xy = avgpooling2d(x * y) - mu_x * mu_y
    k1_square = 0.01 ** 2
    k2_square = 0.03 ** 2
    L_square = 1
    SSIM_n = (2*mu_x*mu_y+k1_square*L_square)*(2*sigma_xy+k2_square*L_square)
    SSIM_d = (mu_x**2+mu_y**2+k1_square*L_square)*(sigma_x+sigma_y+k2_square*L_square)
    SSIM = SSIM_n/SSIM_d
    return torch.clamp((1-SSIM)/2, 0, 1)

def gradient_x(img):
    return img[:,:,:,:-1]-img[:,:,:,1:]

def gradient_y(img):
    return img[:,:,:-1,:]-img[:,:,1:,:]

def pm_loss(alpha, x, y):
    # pm_loss = []
    # for im in x:
    # h, w = x.shape[2:]
    # y = F.interpolate(y, (h, w), mode='bilinear', align_corners=False)
    # pred_seg1 = F.interpolate(pred_seg1, (h, w), mode='bilinear', align_corners=False)
    pm_loss = alpha*(1-pytorch_ssim.ssim(x,y))/2 + (1-alpha)* F.l1_loss(x, y)
    # oseg = torch.abs((pred_seg1-warped_seg1))
    # pm_loss = g
        # pm_loss.append(p_loss)
    # print(pm_loss)
    return pm_loss

def smooth_loss(depth, image):
    h, w = depth.shape[2:]
    image = F.interpolate(image, (h, w), mode='bilinear', align_corners=False)
    # print(depth.size(), image.size())
    gradient_depth_x = gradient_x(depth)
    gradient_depth_y = gradient_y(depth)

    gradient_img_x = gradient_x(image)
    gradient_img_y = gradient_y(image)

    exp_gradient_img_x = torch.exp(-torch.mean(torch.abs(gradient_img_x), 1, True))
    exp_gradient_img_y = torch.exp(-torch.mean(torch.abs(gradient_img_y), 1, True))
    # print(exp_gradient_img_y.size(), exp_gradient_img_x.size())

    smooth_x = gradient_depth_x * exp_gradient_img_x
    smooth_y = gradient_depth_y * exp_gradient_img_y

    return torch.mean(torch.abs(smooth_x))+torch.mean(torch.abs(smooth_y))

def flow_smooth_loss(flow, img):
    smoothness =0
    for i in range(2):
        smoothness += smooth_loss(flow[:,i,:,:].unsqueeze(1),img)
    return smoothness/2

def temporal_consistency_loss(warped_segs, seg):
    # tc_loss = []
    # for war_seg in warped_segs:
    # h, w = warped_segs.shape[2:]
    # large_trace = F.interpolate(seg, (h, w), mode='bilinear', align_corners=False)
    # seg1 = F.interpolate(seg, (h, w), mode='bilinear', align_corners=False)
    tc_loss = F.mse_loss(warped_segs, seg)
        # tc_loss.append(t_loss)
    # tc_loss = sum(tc_loss) / len(warped_segs)
    return tc_loss

def Dice_loss(inputs, targets):
    """
        Compute the DICE loss, similar to generalized IOU for masks
        Args:
            inputs: A float tensor of arbitrary shape.
                    The predictions for each example.
            targets: A float tensor with the same shape as inputs. Stores the binary
                     classification label for each element in inputs
                    (0 for the negative class and 1 for the positive class).
        """
    # inputs = inputs.sigmoid()
    inputs = inputs.flatten(1)
    targets = targets.flatten(1)
    numerator = 2 * (inputs * targets).sum(1)
    denominator = inputs.sum(-1) + targets.sum(-1)
    dicecoef = (numerator + 1) / (denominator + 1)
    loss = 1 - dicecoef.sum() / inputs.size(0)
    return loss


def unsup_loss(pred_flows, warped_imgs1, frame1):

    bce = 0
    smooth = 0
    tc_loss = 0
    seg_loss = 0

    dice_sm = 0
    dice_lg = 0

    bce += 5 * pm_loss(0.85, warped_imgs1[0], frame1)
    smooth += 0.2 * smoothness_loss(pred_flows[0])


    loss = bce + smooth

    return loss, bce, smooth