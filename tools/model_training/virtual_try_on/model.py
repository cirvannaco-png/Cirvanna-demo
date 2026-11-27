"""Cirvanna garment-conditioned warp-and-refine U-Net baseline."""
from __future__ import annotations

def build_model(base_channels:int=48,pose_channels:int=17):
    try:
        import torch
        from torch import nn
        import torch.nn.functional as F
    except ImportError as exc:
        raise RuntimeError("PyTorch must be installed in the approved Try-On training image") from exc

    class ConvBlock(nn.Module):
        def __init__(self,in_channels,out_channels):
            super().__init__()
            groups=min(8,out_channels)
            while out_channels%groups: groups-=1
            self.layers=nn.Sequential(
                nn.Conv2d(in_channels,out_channels,3,padding=1,bias=False),
                nn.GroupNorm(groups,out_channels),nn.SiLU(inplace=True),
                nn.Conv2d(out_channels,out_channels,3,padding=1,bias=False),
                nn.GroupNorm(groups,out_channels),nn.SiLU(inplace=True),
            )
        def forward(self,x): return self.layers(x)

    class CVITryOnWarpNet(nn.Module):
        def __init__(self):
            super().__init__()
            input_channels=3+3+1+1+pose_channels
            self.enc1=ConvBlock(input_channels,base_channels)
            self.enc2=ConvBlock(base_channels,base_channels*2)
            self.enc3=ConvBlock(base_channels*2,base_channels*4)
            self.enc4=ConvBlock(base_channels*4,base_channels*8)
            self.bottleneck=ConvBlock(base_channels*8,base_channels*12)
            self.pool=nn.MaxPool2d(2)
            self.dec4=ConvBlock(base_channels*20,base_channels*8)
            self.dec3=ConvBlock(base_channels*12,base_channels*4)
            self.dec2=ConvBlock(base_channels*6,base_channels*2)
            self.dec1=ConvBlock(base_channels*3,base_channels)
            self.head=nn.Conv2d(base_channels,6,3,padding=1)

        def forward(self,person,garment,person_mask,garment_mask,pose):
            x=torch.cat([person,garment,person_mask,garment_mask,pose],dim=1)
            e1=self.enc1(x)
            e2=self.enc2(self.pool(e1))
            e3=self.enc3(self.pool(e2))
            e4=self.enc4(self.pool(e3))
            mid=self.bottleneck(self.pool(e4))
            d4=self.dec4(torch.cat([F.interpolate(mid,size=e4.shape[-2:],mode="bilinear",align_corners=False),e4],dim=1))
            d3=self.dec3(torch.cat([F.interpolate(d4,size=e3.shape[-2:],mode="bilinear",align_corners=False),e3],dim=1))
            d2=self.dec2(torch.cat([F.interpolate(d3,size=e2.shape[-2:],mode="bilinear",align_corners=False),e2],dim=1))
            d1=self.dec1(torch.cat([F.interpolate(d2,size=e1.shape[-2:],mode="bilinear",align_corners=False),e1],dim=1))
            raw=self.head(d1)
            flow=torch.tanh(raw[:,:2])*0.25
            alpha=torch.sigmoid(raw[:,2:3])
            residual=torch.tanh(raw[:,3:6])*0.15
            height,width=person.shape[-2:]
            ys=torch.linspace(-1,1,height,device=person.device,dtype=person.dtype)
            xs=torch.linspace(-1,1,width,device=person.device,dtype=person.dtype)
            grid_y,grid_x=torch.meshgrid(ys,xs,indexing="ij")
            base_grid=torch.stack([grid_x,grid_y],dim=-1).unsqueeze(0).expand(person.shape[0],-1,-1,-1)
            sampling_grid=(base_grid+flow).clamp(-1.2,1.2)
            warped=F.grid_sample(garment,sampling_grid,mode="bilinear",padding_mode="border",align_corners=True)
            warped_mask=F.grid_sample(garment_mask,sampling_grid,mode="bilinear",padding_mode="zeros",align_corners=True)
            output=(alpha*warped+(1-alpha)*person+residual).clamp(-1,1)
            return {"image":output,"alpha":alpha,"flow":flow,"warped_garment":warped,"warped_garment_mask":warped_mask}

    return CVITryOnWarpNet()

def try_on_loss(outputs,target_image,target_garment_mask):
    import torch
    import torch.nn.functional as F
    image_loss=F.l1_loss(outputs["image"],target_image)
    garment_weight=target_garment_mask.clamp(0,1)
    garment_error=(torch.abs(outputs["image"]-target_image)*garment_weight).sum()/(garment_weight.sum().clamp_min(1.0)*outputs["image"].shape[1])
    mask_loss=F.binary_cross_entropy(outputs["alpha"],garment_weight)
    warp_mask_loss=F.l1_loss(outputs["warped_garment_mask"],garment_weight)
    flow=outputs["flow"]
    smooth_x=torch.abs(flow[:,:,:,1:]-flow[:,:,:,:-1]).mean()
    smooth_y=torch.abs(flow[:,:,1:,:]-flow[:,:,:-1,:]).mean()
    smooth_loss=smooth_x+smooth_y
    total=image_loss+2.0*garment_error+0.5*mask_loss+0.5*warp_mask_loss+0.02*smooth_loss
    return total,{"image_l1":image_loss.detach(),"garment_l1":garment_error.detach(),"mask_bce":mask_loss.detach(),"warp_mask_l1":warp_mask_loss.detach(),"flow_smoothness":smooth_loss.detach()}
