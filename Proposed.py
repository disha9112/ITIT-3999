# Proposed Model

import torch
import torch.nn as nn
import torch.nn.functional as F
from tools import ConvSTFT, ConviSTFT
from config import WIN_LEN, HOP_LEN, FFT_LEN

# causal convolution
class causalConv2d(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size, stride=1, padding=1, dilation=1, groups=1):
        super(causalConv2d, self).__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size, stride=stride, padding=(padding[1], 0),
                              dilation=dilation, groups=groups)
        self.padding = padding[0]

    def forward(self, x):
        x = F.pad(x, [self.padding, 0, 0, 0])
        out = self.conv(x)
        return out

# convolution block
class CONV(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(CONV, self).__init__()
        self.conv = causalConv2d(in_ch, out_ch, kernel_size=(
            3, 2), stride=(2, 1), padding=(1, 1))
        self.ln = nn.GroupNorm(1, out_ch, eps=1e-8)
        self.prelu = nn.PReLU()

    def forward(self, x):
        return self.prelu(self.ln(self.conv(x)))

# convolution block for input layer
class INCONV(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(INCONV, self).__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, kernel_size=1)
        self.ln = nn.GroupNorm(1, out_ch, eps=1e-8)
        self.prelu = nn.PReLU()

    def forward(self, x):
        return self.prelu(self.ln(self.conv(x)))

# sub-pixel convolution block
class SPCONV(nn.Module):
    def __init__(self, in_ch, out_ch, scale_factor=2):
        super(SPCONV, self).__init__()
        self.conv = causalConv2d(
            in_ch, out_ch * scale_factor, kernel_size=(3, 2), padding=(1, 1))
        self.ln = nn.GroupNorm(1, out_ch, eps=1e-8)
        self.prelu = nn.PReLU()

        self.n = scale_factor

    def forward(self, x):
        x = self.conv(x)

        x = x.permute(0, 3, 2, 1)
        r = torch.reshape(x, (x.size(0), x.size(1), x.size(
            2), x.size(3) // self.n, self.n))
        r = r.permute(0, 1, 2, 4, 3)
        r = torch.reshape(r, (x.size(0), x.size(1), x.size(
            2) * self.n, x.size(3) // self.n))
        r = r.permute(0, 3, 2, 1)

        out = self.ln(r)
        out = self.prelu(out)
        return out

# 1x1 conv for down-sampling
class down_sampling(nn.Module):
    def __init__(self, in_ch):
        super(down_sampling, self).__init__()
        self.down_sampling = nn.Conv2d(
            in_ch, in_ch, kernel_size=(3, 1), stride=(2, 1), padding=(1, 0))

    def forward(self, x):
        return self.down_sampling(x)

# 1x1 conv for up-sampling
class upsampling(nn.Module):
    def __init__(self, in_ch):
        super(upsampling, self).__init__()
        self.upsampling = nn.ConvTranspose2d(in_ch, in_ch, kernel_size=(3, 1), stride=(2, 1),
                                             padding=(1, 0), output_padding=(1, 0))

    def forward(self, x):
        out = self.upsampling(x)
        return out

# dilated dense block
class dilatedDenseBlock(nn.Module):
    def __init__(self, in_ch, out_ch, n_layers):
        super(dilatedDenseBlock, self).__init__()

        self.input_layer = causalConv2d(
            in_ch, in_ch // 2, kernel_size=(3, 2), padding=(1, 1))  # channel half
        self.prelu1 = nn.PReLU()

        # dilated dense layer
        self.layers = nn.ModuleList()
        for i in range(n_layers):
            self.caus_padd = ((2 ** i) // 2) * 2
            if i == 0:
                self.caus_padd = 1

            self.layers.append(nn.Sequential(
                # depth-wise separable conv
                causalConv2d(in_ch // 2 + i * in_ch // 2, in_ch // 2, kernel_size=(3, 2),
                             padding=(2 ** i, self.caus_padd), dilation=2 ** i, groups=in_ch // 2),
                # depth-wise
                nn.Conv2d(in_ch // 2, in_ch // 2, kernel_size=1),
                nn.GroupNorm(1, in_ch // 2, eps=1e-8),
                nn.PReLU()
            ))

        self.out_layer = causalConv2d(
            in_ch // 2, out_ch, kernel_size=(3, 2), padding=(1, 1))
        self.prelu2 = nn.PReLU()

    def forward(self, x):
        x = self.input_layer(x)
        x = self.prelu1(x)

        out1 = self.layers[0](x)

        # out2 = self.layers[1](torch.cat([out1, x], dim=1))
        out2 = torch.cat([out1, x], dim=1)
        out2 = self.layers[1](out2)

        # out3 = self.layers[2](torch.cat([out2, out1, x], dim=1))
        out3 = torch.cat([out2, out1], dim=1)
        out3 = torch.cat([out3, x], dim=1)
        out3 = self.layers[2](out3)

        # out4 = self.layers[3](torch.cat([out3, out2, out1, x], dim=1))
        out4 = torch.cat([out3, out2], dim=1)
        out4 = torch.cat([out4, out1], dim=1)
        out4 = torch.cat([out4, x], dim=1)
        out4 = self.layers[3](out4)

        # out5 = self.layers[4](torch.cat([out4, out3, out2, out1, x], dim=1))
        out5 = torch.cat([out4, out3], dim=1)
        out5 = torch.cat([out5, out2], dim=1)
        out5 = torch.cat([out5, out1], dim=1)
        out5 = torch.cat([out5, x], dim=1)
        out5 = self.layers[4](out5)

        # out = self.layers[5](torch.cat([out5, out4, out3, out2, out1, x], dim=1))
        out = torch.cat([out5, out4], dim=1)
        out = torch.cat([out, out3], dim=1)
        out = torch.cat([out, out2], dim=1)
        out = torch.cat([out, out1], dim=1)
        out = torch.cat([out, x], dim=1)
        out = self.layers[5](out)

        out = self.out_layer(out)
        out = self.prelu2(out)

        return out

# Multi-Level Feature Extraction (MLFE) - e6 (for encoder part)
class MLFEe6(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEe6, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch, mid_ch)
        self.en2 = CONV(mid_ch, mid_ch)
        self.en3 = CONV(mid_ch, mid_ch)
        self.en4 = CONV(mid_ch, mid_ch)
        self.en5 = CONV(mid_ch, mid_ch)
        self.en6 = CONV(mid_ch, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, mid_ch)
        self.de4 = SPCONV(mid_ch * 2, mid_ch)
        self.de5 = SPCONV(mid_ch * 2, mid_ch)
        self.de6 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(x)
        out2 = self.en2(out1)
        out3 = self.en3(out2)
        out4 = self.en4(out3)
        out5 = self.en5(out4)
        out6 = self.en6(out5)

        # bottleneck
        out = self.ddense(out6)

        # decoder
        out6 = self.de1(torch.cat([out, out6], dim=1))
        out5 = self.de2(torch.cat([out6, out5], dim=1))
        out4 = self.de3(torch.cat([out5, out4], dim=1))
        out3 = self.de4(torch.cat([out4, out3], dim=1))
        out2 = self.de5(torch.cat([out3, out2], dim=1))
        out1 = self.de6(torch.cat([out2, out1], dim=1))

        out = out1 + x
        return out, out1, out2, out3, out4, out5, out6


# Multi-Level Feature Extraction (MLFE) - e5
class MLFEe5(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEe5, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch, mid_ch)
        self.en2 = CONV(mid_ch, mid_ch)
        self.en3 = CONV(mid_ch, mid_ch)
        self.en4 = CONV(mid_ch, mid_ch)
        self.en5 = CONV(mid_ch, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, mid_ch)
        self.de4 = SPCONV(mid_ch * 2, mid_ch)
        self.de5 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(x)
        out2 = self.en2(out1)
        out3 = self.en3(out2)
        out4 = self.en4(out3)
        out5 = self.en5(out4)

        # bottleneck
        out = self.ddense(out5)

        # decoder
        out5 = self.de1(torch.cat([out, out5], dim=1))
        out4 = self.de2(torch.cat([out5, out4], dim=1))
        out3 = self.de3(torch.cat([out4, out3], dim=1))
        out2 = self.de4(torch.cat([out3, out2], dim=1))
        out1 = self.de5(torch.cat([out2, out1], dim=1))

        out = out1 + x
        return out, out1, out2, out3, out4, out5


# Multi-Level Feature Extraction (MLFE) - e4
class MLFEe4(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEe4, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch, mid_ch)
        self.en2 = CONV(mid_ch, mid_ch)
        self.en3 = CONV(mid_ch, mid_ch)
        self.en4 = CONV(mid_ch, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, mid_ch)
        self.de4 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(x)
        out2 = self.en2(out1)
        out3 = self.en3(out2)
        out4 = self.en4(out3)

        # bottleneck
        out = self.ddense(out4)

        # decoder
        out4 = self.de1(torch.cat([out, out4], dim=1))
        out3 = self.de2(torch.cat([out4, out3], dim=1))
        out2 = self.de3(torch.cat([out3, out2], dim=1))
        out1 = self.de4(torch.cat([out2, out1], dim=1))

        out = out1 + x
        return out, out1, out2, out3, out4


# Multi-Level Feature Extraction (MLFE) - e3
class MLFEe3(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEe3, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch, mid_ch)
        self.en2 = CONV(mid_ch, mid_ch)
        self.en3 = CONV(mid_ch, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(x)
        out2 = self.en2(out1)
        out3 = self.en3(out2)

        # bottleneck
        out = self.ddense(out3)

        # decoder
        out3 = self.de1(torch.cat([out, out3], dim=1))
        out2 = self.de2(torch.cat([out3, out2], dim=1))
        out1 = self.de3(torch.cat([out2, out1], dim=1))

        out = out1 + x
        return out, out1, out2, out3


# Multi-Level Feature Extraction (MLFE) - d6  (for decoder part)
class MLFEd6(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEd6, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch * 2, mid_ch)
        self.en2 = CONV(mid_ch * 2, mid_ch)
        self.en3 = CONV(mid_ch * 2, mid_ch)
        self.en4 = CONV(mid_ch * 2, mid_ch)
        self.en5 = CONV(mid_ch * 2, mid_ch)
        self.en6 = CONV(mid_ch * 2, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, mid_ch)
        self.de4 = SPCONV(mid_ch * 2, mid_ch)
        self.de5 = SPCONV(mid_ch * 2, mid_ch)
        self.de6 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x, ed1, ed2, ed3, ed4, ed5, ed6):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(torch.cat([x, ed1], dim=1))
        out2 = self.en2(torch.cat([out1, ed2], dim=1))
        out3 = self.en3(torch.cat([out2, ed3], dim=1))
        out4 = self.en4(torch.cat([out3, ed4], dim=1))
        out5 = self.en5(torch.cat([out4, ed5], dim=1))
        out6 = self.en6(torch.cat([out5, ed6], dim=1))

        # bottleneck
        out = self.ddense(out6)

        # decoder
        out = self.de1(torch.cat([out, out6], dim=1))
        out = self.de2(torch.cat([out, out5], dim=1))
        out = self.de3(torch.cat([out, out4], dim=1))
        out = self.de4(torch.cat([out, out3], dim=1))
        out = self.de5(torch.cat([out, out2], dim=1))
        out = self.de6(torch.cat([out, out1], dim=1))

        out += x
        return out


# Multi-Level Feature Extraction (MLFE) - d5
class MLFEd5(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEd5, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch * 2, mid_ch)
        self.en2 = CONV(mid_ch * 2, mid_ch)
        self.en3 = CONV(mid_ch * 2, mid_ch)
        self.en4 = CONV(mid_ch * 2, mid_ch)
        self.en5 = CONV(mid_ch * 2, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, mid_ch)
        self.de4 = SPCONV(mid_ch * 2, mid_ch)
        self.de5 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x, ed1, ed2, ed3, ed4, ed5):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(torch.cat([x, ed1], dim=1))
        out2 = self.en2(torch.cat([out1, ed2], dim=1))
        out3 = self.en3(torch.cat([out2, ed3], dim=1))
        out4 = self.en4(torch.cat([out3, ed4], dim=1))
        out5 = self.en5(torch.cat([out4, ed5], dim=1))

        # bottleneck
        out = self.ddense(out5)

        # decoder
        out = self.de1(torch.cat([out, out5], dim=1))
        out = self.de2(torch.cat([out, out4], dim=1))
        out = self.de3(torch.cat([out, out3], dim=1))
        out = self.de4(torch.cat([out, out2], dim=1))
        out = self.de5(torch.cat([out, out1], dim=1))

        out += x
        return out


# Multi-Level Feature Extraction (MLFE) - d4
class MLFEd4(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEd4, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch * 2, mid_ch)
        self.en2 = CONV(mid_ch * 2, mid_ch)
        self.en3 = CONV(mid_ch * 2, mid_ch)
        self.en4 = CONV(mid_ch * 2, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, mid_ch)
        self.de4 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x, ed1, ed2, ed3, ed4):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(torch.cat([x, ed1], dim=1))
        out2 = self.en2(torch.cat([out1, ed2], dim=1))
        out3 = self.en3(torch.cat([out2, ed3], dim=1))
        out4 = self.en4(torch.cat([out3, ed4], dim=1))

        # bottleneck
        out = self.ddense(out4)

        # decoder
        out = self.de1(torch.cat([out, out4], dim=1))
        out = self.de2(torch.cat([out, out3], dim=1))
        out = self.de3(torch.cat([out, out2], dim=1))
        out = self.de4(torch.cat([out, out1], dim=1))

        out += x
        return out


# Multi-Level Feature Extraction (MLFE) - d3
class MLFEd3(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super(MLFEd3, self).__init__()
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = CONV(out_ch * 2, mid_ch)
        self.en2 = CONV(mid_ch * 2, mid_ch)
        self.en3 = CONV(mid_ch * 2, mid_ch)

        # bottleneck
        self.ddense = dilatedDenseBlock(mid_ch, mid_ch, 6)

        # decoder
        self.de1 = SPCONV(mid_ch * 2, mid_ch)
        self.de2 = SPCONV(mid_ch * 2, mid_ch)
        self.de3 = SPCONV(mid_ch * 2, out_ch)

    def forward(self, x, ed1, ed2, ed3):
        x = self.input_layer(x)

        # encoder
        out1 = self.en1(torch.cat([x, ed1], dim=1))
        out2 = self.en2(torch.cat([out1, ed2], dim=1))
        out3 = self.en3(torch.cat([out2, ed3], dim=1))

        # bottleneck
        out = self.ddense(out3)

        # decoder
        out = self.de1(torch.cat([out, out3], dim=1))
        out = self.de2(torch.cat([out, out2], dim=1))
        out = self.de3(torch.cat([out, out1], dim=1))

        out += x
        return out

# Proposed network
class Proposed(nn.Module):

    def __init__(self, in_ch=1, mid_ch=32, out_ch=64):
        super(Proposed, self).__init__()

        # input layer
        self.input_layer = INCONV(in_ch, out_ch)

        # encoder
        self.en1 = MLFEe6(out_ch, mid_ch, out_ch)
        self.down_sampling1 = down_sampling(out_ch)

        self.en2 = MLFEe5(out_ch, mid_ch, out_ch)
        self.down_sampling2 = down_sampling(out_ch)

        self.en3 = MLFEe4(out_ch, mid_ch, out_ch)
        self.down_sampling3 = down_sampling(out_ch)

        self.en4 = MLFEe4(out_ch, mid_ch, out_ch)
        self.down_sampling4 = down_sampling(out_ch)

        self.en5 = MLFEe4(out_ch, mid_ch, out_ch)
        self.down_sampling5 = down_sampling(out_ch)

        self.en6 = MLFEe3(out_ch, mid_ch, out_ch)
        self.down_sampling6 = down_sampling(out_ch)

        # Bottleneck block
        self.DDense = nn.Sequential(
            dilatedDenseBlock(out_ch, out_ch, 6)
        )

        # decoder
        self.upsampling1 = upsampling(out_ch * 2)
        self.de1 = MLFEd3(out_ch * 2, mid_ch, out_ch)

        self.upsampling2 = upsampling(out_ch * 2)
        self.de2 = MLFEd4(out_ch * 2, mid_ch, out_ch)

        self.upsampling3 = upsampling(out_ch * 2)
        self.de3 = MLFEd4(out_ch * 2, mid_ch, out_ch)

        self.upsampling4 = upsampling(out_ch * 2)
        self.de4 = MLFEd4(out_ch * 2, mid_ch, out_ch)

        self.upsampling5 = upsampling(out_ch * 2)
        self.de5 = MLFEd5(out_ch * 2, mid_ch, out_ch)

        self.upsampling6 = upsampling(out_ch * 2)
        self.de6 = MLFEd6(out_ch * 2, mid_ch, out_ch)

        # output layer
        self.output_layer = nn.Conv2d(out_ch, in_ch, kernel_size=1)

        # for feature extract
        self.stft = ConvSTFT(WIN_LEN, HOP_LEN, FFT_LEN, feature_type='real')
        self.istft = ConviSTFT(WIN_LEN, HOP_LEN, FFT_LEN, feature_type='real')

    def forward(self, x):
        # STFT
        mags, phase = self.stft(x)
        hx = mags.unsqueeze(1)
        hx = hx[:, :, 1:]

        # input layer
        hx = self.input_layer(hx)

        # encoder stage 1
        hx1, hx1_1, hx1_2, hx1_3, hx1_4, hx1_5, hx1_6 = self.en1(hx)
        hx1 = self.down_sampling1(hx1)

        # encoder stage 2
        hx2, hx2_1, hx2_2, hx2_3, hx2_4, hx2_5 = self.en2(hx1)
        hx2 = self.down_sampling2(hx2)

        # encoder stage 3
        hx3, hx3_1, hx3_2, hx3_3, hx3_4 = self.en3(hx2)
        hx3 = self.down_sampling3(hx3)

        # encoder stage 4
        hx4, hx4_1, hx4_2, hx4_3, hx4_4 = self.en4(hx3)
        hx4 = self.down_sampling4(hx4)

        # encoder stage 5
        hx5, hx5_1, hx5_2, hx5_3, hx5_4 = self.en5(hx4)
        hx5 = self.down_sampling5(hx5)

        # encoder stage 6
        hx6, hx6_1, hx6_2, hx6_3 = self.en6(hx5)
        hx6 = self.down_sampling6(hx6)

        # dilated dense block
        out = self.DDense(hx6)

        # decoder stage 1
        out = self.upsampling1(torch.cat([out, hx6], dim=1))
        out = self.de1(out, hx6_1, hx6_2, hx6_3)

        # decoder stage 2
        out = self.upsampling2(torch.cat([out, hx5], dim=1))
        out = self.de2(out, hx5_1, hx5_2, hx5_3, hx5_4)

        # decoder stage 3
        out = self.upsampling3(torch.cat([out, hx4], dim=1))
        out = self.de3(out, hx4_1, hx4_2, hx4_3, hx4_4)

        # decoder stage 4
        out = self.upsampling4(torch.cat([out, hx3], dim=1))
        out = self.de4(out, hx3_1, hx3_2, hx3_3, hx3_4)

        # decoder stage 5
        out = self.upsampling5(torch.cat([out, hx2], dim=1))
        out = self.de5(out, hx2_1, hx2_2, hx2_3, hx2_4, hx2_5)

        # decoder stage 6
        out = self.upsampling6(torch.cat([out, hx1], dim=1))
        out = self.de6(out, hx1_1, hx1_2, hx1_3, hx1_4, hx1_5, hx1_6)

        # output layer
        out = self.output_layer(out)

        out = F.pad(out, [0, 0, 1, 0])

        # ISTFT
        out_wav = self.istft(out.squeeze(1), phase).squeeze(1)
        out_wav = torch.clamp_(out_wav, -1, 1)  # clipping [-1, 1]
        return out_wav

    def loss(self, enhanced, target):
        calc_loss = F.mse_loss(enhanced, target.view(-1, 1), reduction='mean')
        print(calc_loss)
        return calc_loss
