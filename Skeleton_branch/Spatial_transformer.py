import math
from einops import rearrange
import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.nn.functional as F


def import_class(name):
    components = name.split('.')
    mod = __import__(components[0])
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod


def conv_branch_init(conv, branches):
    weight = conv.weight
    n = weight.size(0)
    k1 = weight.size(1)
    k2 = weight.size(2)
    nn.init.normal_(weight, 0, math.sqrt(2. / (n * k1 * k2 * branches)))
    nn.init.constant_(conv.bias, 0)


def conv_init(conv):
    nn.init.kaiming_normal_(conv.weight, mode='fan_out')
    nn.init.constant_(conv.bias, 0)


def bn_init(bn, scale):
    nn.init.constant_(bn.weight, scale)
    nn.init.constant_(bn.bias, 0)

class unit_tcn(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=9, stride=1):
        super(unit_tcn, self).__init__()

        pad = int((kernel_size - 1) / 2)
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=(kernel_size, 1), padding=(pad, 0),
                                stride=(stride, 1))

        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()
        conv_init(self.conv)
        bn_init(self.bn, 1)

    def forward(self, x):
        x = self.bn(self.conv(x))
        return x


class unit_tcn_m(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1, kernel_size=[1, 3, 7]):        # ks=9 initial
        super(unit_tcn_m, self).__init__()

        pad1 = int((kernel_size[0] - 1) / 2)
        pad2 = int((kernel_size[1] - 1) / 2)
        pad3 = int((kernel_size[2] - 1) / 2)

        mid_channels = out_channels//3

        self.conv11 = nn.Conv2d(in_channels, in_channels, kernel_size=(1, 1))
        self.conv21 = nn.Conv2d(in_channels, in_channels, kernel_size=(1, 1))
        self.conv31 = nn.Conv2d(in_channels, in_channels, kernel_size=(1, 1))

        self.conv12 = nn.Conv2d(in_channels, mid_channels, kernel_size=(kernel_size[0], 1), padding=(pad1, 0),
                                stride=(stride, 1))
        self.conv22 = nn.Conv2d(in_channels, mid_channels, kernel_size=(kernel_size[1], 1), padding=(pad2, 0),
                                stride=(stride, 1))
        self.conv32 = nn.Conv2d(in_channels, mid_channels, kernel_size=(kernel_size[2], 1), padding=(pad3, 0),
                                stride=(stride, 1))

        self.bn = nn.BatchNorm2d(out_channels)
        conv_init(self.conv11)
        conv_init(self.conv21)
        conv_init(self.conv31)
        conv_init(self.conv12)
        conv_init(self.conv22)
        conv_init(self.conv32)
        bn_init(self.bn, 1)

    def forward(self, x):
        x1 = self.conv12(self.conv11(x))
        x2 = self.conv22(self.conv21(x))
        x3 = self.conv32(self.conv31(x))
        x = torch.cat([x1, x2, x3], dim=1)
        x  = self.bn(x)
        return x


class unit_gcn(nn.Module):
    def __init__(self, in_channels, out_channels, A, coff_embedding=4, num_subset=3):
        super(unit_gcn, self).__init__()
        inter_channels = out_channels // coff_embedding
        self.inter_c = inter_channels
        self.PA = nn.Parameter(torch.from_numpy(A.astype(np.float32)))
        nn.init.constant_(self.PA, 1e-6)
        self.A = Variable(torch.from_numpy(A.astype(np.float32)), requires_grad=False)
        self.num_subset = num_subset

        self.conv_a = nn.ModuleList()
        self.conv_b = nn.ModuleList()
        self.conv_d = nn.ModuleList()
        for i in range(self.num_subset):
            self.conv_a.append(nn.Conv2d(in_channels, inter_channels, 1))
            self.conv_b.append(nn.Conv2d(in_channels, inter_channels, 1))
            self.conv_d.append(nn.Conv2d(in_channels, out_channels, 1))

        if in_channels != out_channels:
            self.down = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1),
                nn.BatchNorm2d(out_channels)
            )
        else:
            self.down = lambda x: x

        self.bn = nn.BatchNorm2d(out_channels)
        self.soft = nn.Softmax(-2)
        self.relu = nn.ReLU()

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                conv_init(m)
            elif isinstance(m, nn.BatchNorm2d):
                bn_init(m, 1)
        bn_init(self.bn, 1e-6)
        for i in range(self.num_subset):
            conv_branch_init(self.conv_d[i], self.num_subset)

    def forward(self, x):
        # batchsize, channel, t, node_num
        N, C, T, V = x.size()
        #print(N, C, T, V)
        A = self.A.cuda(x.get_device())
        A = A + self.PA

        y = None
        for i in range(self.num_subset):
            A1 = self.conv_a[i](x).permute(0, 3, 1, 2).contiguous().view(N, V, self.inter_c * T)
            A2 = self.conv_b[i](x).view(N, self.inter_c * T, V)
            A1 = self.soft(torch.matmul(A1, A2) / A1.size(-1))  # N V V
            A1 = A1 + A[i]
            A2 = x.view(N, C * T, V)
            z = self.conv_d[i](torch.matmul(A2, A1).view(N, C, T, V))
            y = z + y if y is not None else z

        y = self.bn(y)
        y += self.down(x)
        return self.relu(y)


class TCN_GCN_unit(nn.Module):

    def __init__(self, in_channels, out_channels, A, stride=1, residual=True):
        super(TCN_GCN_unit, self).__init__()
        self.gcn1 = unit_gcn(in_channels, out_channels, A)
        self.tcn1 = unit_tcn_m(out_channels, out_channels, stride=stride)
        self.relu = nn.ReLU()
        if not residual:
            self.residual = lambda x: 0

        elif (in_channels == out_channels) and (stride == 1):
            self.residual = lambda x: x

        else:
            self.residual = unit_tcn(in_channels, out_channels, kernel_size=1, stride=stride)

    def forward(self, x):
        x = self.tcn1(self.gcn1(x)) + self.residual(x)
        return self.relu(x)


class Residual(nn.Module):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
    def forward(self, x, **kwargs):
        return self.fn(x, **kwargs) + x

class LayerNormalize(nn.Module):
    def __init__(self, dim, fn):
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.fn = fn
    def forward(self, x, **kwargs):
        return self.fn(self.norm(x), **kwargs)

class MLP_Block(nn.Module):
    def __init__(self, dim, hid_dim, dropout = 0.1):
        super().__init__()
        self.nn1 = nn.Linear(dim, hid_dim)
        torch.nn.init.xavier_uniform_(self.nn1.weight)
        torch.nn.init.normal_(self.nn1.bias, std = 1e-6)
        self.af1 = nn.ReLU()
        self.do1 = nn.Dropout(dropout)
        self.nn2 = nn.Linear(hid_dim, dim)
        torch.nn.init.xavier_uniform_(self.nn2.weight)
        torch.nn.init.normal_(self.nn2.bias, std = 1e-6)
        self.do2 = nn.Dropout(dropout)
        
    def forward(self, x):
        x = self.nn1(x)
        x = self.af1(x)
        x = self.do1(x)
        x = self.nn2(x)
        x = self.do2(x)
        
        return x

 #################################################################333

class Attention(nn.Module):
    def __init__(self, dim, out_dim, heads=3, dropout=0.1, num_point=17):
        super().__init__()
        self.heads = heads
        self.scale = dim ** -0.5

        self.num_point = num_point

        self.to_qkv = nn.Linear(dim, dim*3, bias=True)
        torch.nn.init.xavier_uniform_(self.to_qkv.weight)
        torch.nn.init.zeros_(self.to_qkv.bias)

        self.nn1 = nn.Linear(dim, out_dim)
        torch.nn.init.xavier_uniform_(self.nn1.weight)
        torch.nn.init.zeros_(self.nn1.bias)

        self.do1 = nn.Dropout(dropout)
        
        self.key_rel = nn.Parameter(torch.randn(((num_point ** 2) - num_point, dim // heads)) * 0.02, requires_grad=True)
        self.key_rel_diagonal = nn.Parameter(torch.randn((1, dim // heads)) * 0.02, requires_grad=True)

    def forward(self, x, mask=None, T=1):
        b, n, _, h = *x.shape, self.heads
        assert n == self.num_point, f"Expected n={self.num_point}, got {n}"
        qkv = self.to_qkv(x)
        q, k, v = rearrange(qkv, 'b n (qkv h d) -> qkv b h n d', qkv=3, h=h)
        dots = torch.einsum('bhid,bhjd->bhij', q, k) * self.scale
        if mask is not None:
            assert mask.shape[-1] == dots.shape[-1], 'mask has incorrect dimensions'
            dots = dots + mask
        rel_logits = self.relative_logits(q, T=T) * self.scale
        if self.training:
            rel_logits = F.dropout(rel_logits, p=0.1)
        dots_sum = torch.add(dots, rel_logits)
        attn = dots_sum.softmax(dim=-1)
        out = torch.einsum('bhij,bhjd->bhid', attn, v)
        out = rearrange(out, 'b h n d -> b n (h d)')
        out = self.nn1(out)
        out = self.do1(out)
        return out


    def relative_logits(self, q, T=1):
        B_T, Nh, V, dk = q.size()
        assert B_T % T == 0, f"B*T={B_T} not divisible by T={T}"
        B = B_T // T

        q = q.view(B, T, Nh, V, dk).permute(0, 2, 4, 1, 3)  # (B, Nh, dk, T, V)
        assert q.size() == (B, Nh, dk, T, V), f"Expected shape {(B, Nh, dk, T, V)}, got {q.size()}"

        q = torch.transpose(q, 2, 4).transpose(2, 3)  # (B, Nh, T, V, dk)
        q_first = q.unsqueeze(4).expand((B, Nh, T, V, V - 1, dk))
        q_first = torch.reshape(q_first, (B * Nh * T, -1, dk))

        q = torch.reshape(q, (B * Nh * T, V, dk))
        param_diagonal = self.key_rel_diagonal.to(q.device).expand((V, dk))
        rel_logits = self.relative_logits_1d(q_first, q, self.key_rel.to(q.device), param_diagonal, T, V, Nh)
        return rel_logits

    def relative_logits_1d(self, q_first, q, rel_k, param_diagonal, T, V, Nh):
        rel_logits = torch.einsum('bmd,md->bm', q_first, rel_k)
        rel_logits_diagonal = torch.einsum('bmd,md->bm', q, param_diagonal)
        rel_logits = self.rel_to_abs(rel_logits, rel_logits_diagonal)
        rel_logits = torch.reshape(rel_logits, (-1, Nh, V, V))
        return rel_logits

    def rel_to_abs(self, rel_logits, rel_logits_diagonal):
        B, L = rel_logits.size()
        B, V = rel_logits_diagonal.size()
        rel_logits = torch.reshape(rel_logits, (B, V - 1, V))
        row_pad = torch.zeros(B, 1, V).to(rel_logits)
        rel_logits = torch.cat((rel_logits, row_pad), dim=1)
        rel_logits_diagonal = torch.reshape(rel_logits_diagonal, (B, V, 1))
        rel_logits = torch.cat((rel_logits_diagonal, rel_logits), dim=2)
        rel_logits = torch.reshape(rel_logits, (B, V + 1, V))
        flat_sliced = rel_logits[:, :V, :]
        final_x = torch.reshape(flat_sliced, (B, V, V))
        return final_x

    # ... (relative_logits, relative_logits_1d, rel_to_abs unchanged)

class Transformer(nn.Module):
    def __init__(self, dim, depth, heads, mlp_dim, dropout=0.1, num_point=17):
        super().__init__()
        self.layers = nn.ModuleList([])
        if dim == mlp_dim:
            for _ in range(depth):
                self.layers.append(nn.ModuleList([
                    Residual(Attention(dim, mlp_dim, heads=heads, dropout=dropout, num_point=num_point)),
                    Residual(LayerNormalize(mlp_dim, MLP_Block(mlp_dim, mlp_dim*2, dropout=dropout)))
                ]))
        else:
            for _ in range(depth):
                self.layers.append(nn.ModuleList([
                    Attention(dim, mlp_dim, heads=heads, dropout=dropout, num_point=num_point),
                    Residual(LayerNormalize(mlp_dim, MLP_Block(mlp_dim, mlp_dim*2, dropout=dropout)))
                ]))
    def forward(self, x, mask=None, T=1):
        for attention, mlp in self.layers:
            x = attention(x, mask=mask, T=T)
            x = mlp(x)
        return x

class TCN_STRANSF_unit(nn.Module):
    def __init__(self, in_channels, out_channels, num_point, heads=3, stride=1, residual=True, dropout=0.1, mask=None, mask_grad=True):
        super().__init__()
        self.transf1 = Transformer(dim=in_channels, depth=1, heads=heads, mlp_dim=in_channels, dropout=dropout, num_point=num_point)
        self.tcn1 = unit_tcn_m(in_channels, out_channels, stride=stride)
        self.relu = nn.ReLU()
        self.out_channels = out_channels
        if not residual:
            self.residual = lambda x: 0
        elif (in_channels == out_channels) and (stride == 1):
            self.residual = lambda x: x
        else:
            self.residual = unit_tcn(in_channels, out_channels, kernel_size=1, stride=stride)
        if mask is not None:
            self.mask = nn.Parameter(mask, requires_grad=mask_grad)

    def forward(self, x, mask=None, T=1):
        B, C, T_, V = x.size()
        # Adjust T to match T_ if the passed T is from a previous layer's input
        if T_ != T:
            T = T_
        assert T_ == T, f"Expected T={T}, got T_={T_}"
        tx = x.permute(0, 2, 3, 1).contiguous().view(B * T, V, C)
        if mask is None and hasattr(self, 'mask'):
            tx = self.transf1(tx, self.mask, T=T)
        else:
            tx = self.transf1(tx, mask, T=T)
        tx = tx.view(B, T, V, C).permute(0, 3, 1, 2).contiguous()
        x = self.tcn1(tx) + self.residual(x)
        return self.relu(x)

###############################################################################################

class ZiT(nn.Module):
    def __init__(self, in_channels=3, num_person=12, num_point=17, num_head=6, graph=None, graph_args=dict()):
        super(ZiT, self).__init__()
        self.data_bn = nn.BatchNorm1d(num_person * in_channels * num_point)
        bn_init(self.data_bn, 1)
        self.heads = num_head
        if graph is None:
            raise ValueError()
        else:
            Graph = import_class(graph)
            self.graph = Graph(**graph_args)
        self.A = torch.from_numpy(self.graph.A[0].astype(np.float32)).unsqueeze(0).repeat(num_head, 1, 1)
        self.l1 = TCN_GCN_unit(3, 48, self.graph.A, residual=False)
        self.l2 = TCN_STRANSF_unit(48, 48, num_point=num_point, heads=num_head, mask=self.A, mask_grad=False)
        self.l3 = TCN_STRANSF_unit(48, 48, num_point=num_point, heads=num_head, mask=self.A, mask_grad=False)
        self.l4 = TCN_STRANSF_unit(48, 96, num_point=num_point, heads=num_head, stride=2, mask=self.A, mask_grad=True)
        self.l5 = TCN_STRANSF_unit(96, 96, num_point=num_point, heads=num_head, mask=self.A, mask_grad=True)
        self.l6 = TCN_STRANSF_unit(96, 192, num_point=num_point, heads=num_head, stride=2, mask=self.A, mask_grad=True)
        self.l7 = TCN_STRANSF_unit(192, 192, num_point=num_point, heads=num_head, mask=self.A, mask_grad=True)

    def forward(self, x):
        N, C, T, V, M = x.size()
        x = x.permute(0, 4, 3, 1, 2).contiguous().view(N, M * V * C, T)
        x = self.data_bn(x)
        x = x.view(N, M, V, C, T).permute(0, 1, 3, 4, 2).contiguous().view(N * M, C, T, V)
        current_T = T
        x = self.l1(x)
        x = self.l2(x, T=current_T)
        x = self.l3(x, T=current_T)
        x = self.l4(x, T=current_T)  # T remains 10
        current_T = current_T // 2  # Adjust T after stride=2
        x = self.l5(x, T=current_T)  # T=5
        x = self.l6(x, T=current_T)  # T=5
        current_T = current_T // 2  # Adjust T after stride=2
        x = self.l7(x, T=current_T)  # T=2
        B, C_, T_, V_ = x.size()
        x = x.view(N, M, C_, T_, V_).mean(4)
        x = x.permute(0, 2, 3, 1).contiguous()
        return x

# ... (ZoT, Model unchanged)

class ZoT(nn.Module):
    def __init__(self, num_class=15, num_head=6,num_person=2):
        super(ZoT, self).__init__()

        self.heads = num_head

        self.conv1 = nn.Conv2d(192, num_head, kernel_size=(1, 1))
        self.conv2 = nn.Conv2d(192, num_head, kernel_size=(1, 1))
        conv_init(self.conv1)
        conv_init(self.conv2)

        self.l1 = TCN_STRANSF_unit(192, 276, num_point=num_person, heads=num_head)
        self.l2 = TCN_STRANSF_unit(276, 276, num_point=num_person, heads=num_head)

        self.fc = nn.Linear(276, num_class)
        nn.init.normal_(self.fc.weight, 0, math.sqrt(2. / num_class))
    
    def forward(self, x):
        # N,C,T,M
        x1 = self.conv1(x)
        x2 = self.conv2(x)
        x1 = x1.unsqueeze(3)
        x2 = x2.unsqueeze(4)
        mask = x1-x2
        N, C, T, M, M2 = mask.shape
        mask = mask.permute(0, 2, 1, 3, 4).contiguous().view(N*T, C, M, M2).detach()
        mask = mask.softmax(dim=-1)


        x = self.l1(x, mask)
        x = self.l2(x, mask)
        x = x.mean(3).mean(2)

        return self.fc(x)

class Model(nn.Module):
    def __init__(self, num_class=60, in_channels=3, num_person=2, num_point=17, num_head=6, graph=None, graph_args=dict()):
        super(Model, self).__init__()

        self.body_transf = ZiT(in_channels=in_channels, num_person=num_person, num_point=num_point, num_head=num_head, graph=graph, graph_args=graph_args)
        self.group_transf = ZoT(num_class=num_class, num_head=num_head,num_person=num_person)


    def forward(self, x):
        x = self.body_transf(x)
        x = self.group_transf(x)

        return x
