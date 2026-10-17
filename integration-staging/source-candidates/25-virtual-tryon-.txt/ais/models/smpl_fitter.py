import torch
import torch.nn.functional as F
import smplx
import numpy as np
from pytorch3d.structures import Meshes
from pytorch3d.renderer import (
    PerspectiveCameras, RasterizationSettings, MeshRenderer,
    MeshRasterizer, SoftSilhouetteShader, TexturesVertex
)
import mlflow.pytorch
import os

class SMPLFitter:
    def __init__(self, config):
        self.config = config
        self.device = torch.device(
            f"cuda:{config.gpu_device}" if config.gpu_enabled and torch.cuda.is_available() else "cpu"
        )
        self.smpl = smplx.create(
            config.smpl_model_path,
            model_type='smpl',
            gender='neutral',
            num_betas=10,
            use_face_contour=False
        ).to(self.device)

        # Setup differentiable renderer
        self.raster_settings = RasterizationSettings(image_size=512, blur_radius=0.0, faces_per_pixel=1)
        self.renderer = MeshRenderer(
            rasterizer=MeshRasterizer(raster_settings=self.raster_settings),
            shader=SoftSilhouetteShader()
        ).to(self.device)

        # Load measurement regressor from MLflow
        self.measurement_regressor = None
        try:
            model_uri = "models:/MeasurementRegressor/production"
            self.measurement_regressor = mlflow.pytorch.load_model(model_uri, map_location=self.device)
            self.measurement_regressor.eval()
            print("Loaded measurement regressor from MLflow")
        except Exception as e:
            print(f"Could not load measurement regressor: {e}. Using heuristic fallback.")

    def fit_multiview(
        self,
        images,
        masks,
        keypoints,
        height_cm,
        focal_length,
        sensor_size,
        weight_kg=None
    ):
        batch_size = len(images)
        H, W = images[0].shape[:2]

        # Convert to tensors
        masks_t = [torch.from_numpy(m).float().to(self.device) for m in masks]
        keypoints_t = []
        for kp in keypoints:
            # keypoints: (17,3) with last column confidence
            kp_xy = torch.from_numpy(kp[:, :2]).float().to(self.device) * H
            keypoints_t.append(kp_xy)

        # Setup cameras (simplified: assume frontal view with identity rotation)
        focal_pixels = focal_length * max(W, H) / max(sensor_size)
        cameras = []
        for i in range(batch_size):
            camera = PerspectiveCameras(
                focal_length=((focal_pixels, focal_pixels),),
                principal_point=((W/2, H/2),),
                image_size=((H, W),),
                device=self.device
            )
            cameras.append(camera)

        # Initialize SMPL parameters
        betas = torch.zeros(10, requires_grad=True, device=self.device)
        body_pose = torch.zeros(23*3, requires_grad=True, device=self.device)
        global_orient = torch.zeros(3, requires_grad=True, device=self.device)
        transl = torch.zeros(3, requires_grad=True, device=self.device)

        optimizer = torch.optim.Adam(
            [betas, body_pose, global_orient, transl],
            lr=self.config.smpl_learning_rate
        )

        # Pre-load faces once
        faces = torch.tensor(self.smpl.faces.astype(np.int64), device=self.device).unsqueeze(0)

        for step in range(self.config.smpl_optimization_steps):
            optimizer.zero_grad()

            # Forward SMPL
            smpl_output = self.smpl(
                betas=betas.unsqueeze(0),
                body_pose=body_pose.unsqueeze(0),
                global_orient=global_orient.unsqueeze(0),
                transl=transl.unsqueeze(0)
            )
            vertices = smpl_output.vertices[0]  # (V, 3)
            joints = smpl_output.joints[0]      # (J, 3)

            # Create PyTorch3D mesh
            textures = TexturesVertex(verts_features=torch.ones_like(vertices).unsqueeze(0))
            mesh = Meshes(verts=[vertices], faces=faces, textures=textures)

            loss = 0.0

            # Silhouette and landmark losses per view
            for i, cam in enumerate(cameras):
                # Render silhouette
                silhouette = self.renderer(mesh, cameras=cam)[..., 3]  # alpha channel
                loss += self.config.silhouette_weight * F.mse_loss(silhouette, masks_t[i])

                # Project joints
                proj_joints = cam.transform_points_screen(joints.unsqueeze(0))[0, :, :2]
                # Use only first 17 joints (SMPL joints order may differ)
                loss += self.config.landmark_weight * F.mse_loss(proj_joints[:17], keypoints_t[i])

            # Height constraint
            verts_y = vertices[:, 1]
            height = verts_y.max() - verts_y.min()
            height_m = height * 100  # convert to cm
            loss += self.config.height_weight * (height_m - height_cm) ** 2

            loss.backward()
            optimizer.step()

        # Extract measurements from final mesh
        measurements = self._extract_measurements(vertices, betas, height_cm)

        return vertices.detach().cpu().numpy(), measurements

    def _extract_measurements(self, vertices, betas, height_cm):
        if self.measurement_regressor is not None:
            with torch.no_grad():
                betas_tensor = betas.detach().cpu().unsqueeze(0).float()
                raw_meas = self.measurement_regressor(betas_tensor).squeeze().numpy()
            meas_dict = {
                'chest_cm': raw_meas[0],
                'waist_cm': raw_meas[1],
                'hip_cm': raw_meas[2],
                'shoulder_cm': raw_meas[3],
                'torso_length_cm': raw_meas[4],
                'inseam_cm': raw_meas[5],
                'arm_length_cm': raw_meas[6],
                'thigh_cm': raw_meas[7],
                'calf_cm': raw_meas[8],
                'neck_cm': raw_meas[9],
                'wrist_cm': raw_meas[10],
                'ankle_cm': raw_meas[11],
                'bicep_cm': raw_meas[12],
            }
            scale = height_cm / 170.0
            for k in meas_dict:
                meas_dict[k] *= scale
            return meas_dict
        else:
            return self._extract_measurements_heuristic(betas, height_cm)

    def _extract_measurements_heuristic(self, betas, height_cm):
        betas_np = betas.detach().cpu().numpy()
        measurements = {
            'chest_cm': 90.0 + betas_np[0] * 10,
            'waist_cm': 75.0 + betas_np[1] * 8,
            'hip_cm': 95.0 + betas_np[2] * 8,
            'shoulder_cm': 42.0 + betas_np[3] * 5,
            'torso_length_cm': 50.0 + betas_np[4] * 4,
            'inseam_cm': 78.0 + betas_np[5] * 6,
            'arm_length_cm': 60.0 + betas_np[6] * 4,
        }
        scale = height_cm / 170.0
        for k in measurements:
            measurements[k] *= scale
        return measurements
