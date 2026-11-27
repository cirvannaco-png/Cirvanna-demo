"""Cirvanna parametric body geometry reconstructed from a registered scan basis."""
from __future__ import annotations
import numpy as np

def reconstruct_mesh(mean_vertices: np.ndarray, shape_basis: np.ndarray, coefficients: np.ndarray, faces: np.ndarray):
    mean=np.asarray(mean_vertices,dtype=np.float64)
    basis=np.asarray(shape_basis,dtype=np.float64)
    coeff=np.asarray(coefficients,dtype=np.float64)
    triangles=np.asarray(faces,dtype=np.int64)
    if mean.ndim!=2 or mean.shape[1]!=3:
        raise ValueError("mean_vertices must have shape (N,3)")
    if basis.ndim!=3 or basis.shape[1:]!=mean.shape:
        raise ValueError("shape_basis must have shape (K,N,3)")
    if coeff.ndim!=1 or len(coeff)!=len(basis):
        raise ValueError("coefficient vector dimension must match shape basis")
    if triangles.ndim!=2 or triangles.shape[1]!=3 or np.any(triangles<0) or np.any(triangles>=len(mean)):
        raise ValueError("faces must be valid triangle indices")
    if not np.isfinite(mean).all() or not np.isfinite(basis).all() or not np.isfinite(coeff).all():
        raise ValueError("geometry inputs must be finite")
    vertices=mean+np.tensordot(coeff,basis,axes=(0,0))
    return vertices,triangles.copy()

def export_mesh_only_glb(vertices: np.ndarray, faces: np.ndarray) -> tuple[bytes, dict[str, object]]:
    """Serialize a private, texture-free GLB candidate and enforce closed topology."""
    import trimesh
    mesh=trimesh.Trimesh(
        vertices=np.asarray(vertices,dtype=np.float32),
        faces=np.asarray(faces,dtype=np.int64),
        vertex_colors=np.tile(np.asarray([[145,145,145,255]],dtype=np.uint8),(len(vertices),1)),
        process=False,
    )
    mesh.fix_normals(multibody=True)
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError("parametric body mesh must be watertight and consistently wound before GLB export")
    extents=np.asarray(mesh.bounding_box.extents,dtype=np.float64)
    if not np.isfinite(extents).all() or np.any(extents<=1e-5):
        raise ValueError("parametric body mesh has degenerate extents")
    data=mesh.export(file_type="glb")
    if not isinstance(data,bytes) or not data.startswith(b"glTF"):
        raise ValueError("GLB serialization failed")
    return data,{
        "vertex_count":int(len(mesh.vertices)),
        "triangle_count":int(len(mesh.faces)),
        "watertight":bool(mesh.is_watertight),
        "winding_consistent":bool(mesh.is_winding_consistent),
        "extents_mm":extents.tolist(),
        "embedded_textures":False,
    }
