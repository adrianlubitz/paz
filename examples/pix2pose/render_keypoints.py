from paz import processors as pr
from paz.pipelines import RandomizeRenderedImage
import numpy as np

import numpy as np
from paz.backend.render import sample_uniformly, split_alpha_channel
from paz.backend.render import random_perturbation, sample_point_in_sphere
from paz.backend.render import compute_modelview_matrices
from pyrender import PerspectiveCamera, OffscreenRenderer, DirectionalLight
from pyrender import RenderFlags, Mesh, Scene
import trimesh


class DrawNormalizedKeypoints(pr.Processor):
    def __init__(self, num_keypoints, radius=3, image_normalized=False):
        super(DrawNormalizedKeypoints, self).__init__()
        self.denormalize = pr.DenormalizeKeypoints()
        self.remove_depth = pr.RemoveKeypointsDepth()
        self.draw = pr.DrawKeypoints2D(num_keypoints, radius, image_normalized)

    def call(self, image, keypoints):
        keypoints = self.denormalize(keypoints, image)
        keypoints = self.remove_depth(keypoints)
        image = self.draw(image, keypoints)
        return image


class SingleView():
    """Render-ready scene composed of a single object and a single moving camera.

    # Arguments
        filepath: String containing the path to an OBJ file.
        viewport_size: List, specifying [H, W] of rendered image.
        y_fov: Float indicating the vertical field of view in radians.
        distance: List of floats indicating [max_distance, min_distance]
        light: List of floats indicating [max_light, min_light]
        top_only: Boolean. If True images are only take from the top.
        roll: Float, to sample [-roll, roll] rolls of the Z OpenGL camera axis.
        shift: Float, to sample [-shift, shift] to move in X, Y OpenGL axes.
    """
    def __init__(self, filepath, viewport_size=(128, 128), y_fov=3.14159 / 4.0,
                 distance=[0.3, 0.5], light=[0.5, 30], top_only=False,
                 roll=None, shift=None):
        self.distance, self.roll, self.shift = distance, roll, shift
        self.light_intensity, self.top_only = light, top_only
        self._build_scene(filepath, viewport_size, light, y_fov)
        self.renderer = OffscreenRenderer(viewport_size[0], viewport_size[1])
        self.viewport_size = viewport_size
        self.RGBA = RenderFlags.RGBA
        self.epsilon = 0.01

    def _build_scene(self, path, size, light, y_fov):
        self.scene = Scene(bg_color=[0, 0, 0, 0])
        self.light = self.scene.add(
            DirectionalLight([1.0, 1.0, 1.0], np.mean(light)))
        self.camera = self.scene.add(
            PerspectiveCamera(y_fov, aspectRatio=np.divide(*size)))
        self.mesh = self.scene.add(
            Mesh.from_trimesh(trimesh.load(path), smooth=True))
        self.world_origin = self.mesh.mesh.centroid

    def _sample_parameters(self):
        distance = sample_uniformly(self.distance)
        camera_origin = sample_point_in_sphere(distance, self.top_only)
        camera_origin = random_perturbation(camera_origin, self.epsilon)
        light_intensity = sample_uniformly(self.light_intensity)
        return camera_origin, light_intensity

    def render(self):
        camera_origin, intensity = self._sample_parameters()
        camera_to_world, world_to_camera = compute_modelview_matrices(
            camera_origin, self.world_origin, self.roll, self.shift)
        self.light.light.intensity = intensity
        self.scene.set_pose(self.camera, camera_to_world)
        self.scene.set_pose(self.light, camera_to_world)
        image, depth = self.renderer.render(self.scene, flags=self.RGBA)
        image, alpha = split_alpha_channel(image)
        return image, alpha, world_to_camera


def project(xyzw, focal_length):
    z = xyzw[:, :, 2:3] + 1e-8
    x = - (focal_length / z) * xyzw[:, :, 0:1]
    y = - (focal_length / z) * xyzw[:, :, 1:2]
    return np.concatenate([x, y, z], axis=2)


def project_keypoints(keypoints, world_to_camera):
    """Projects homogenous keypoints (4D) in the camera coordinates system
        into image coordinates using a projective transformation.

    # Arguments
        keypoints: Numpy array of shape ''(num_keypoints, 3)''
    """
    keypoints = np.matmul(keypoints, world_to_camera.T)
    keypoints = np.expand_dims(keypoints, 0)
    keypoints = project(keypoints)[0]
    return keypoints


def render_random_sample(render, augment, keypoints):
    image, alpha_mask, world_to_camera = render()
    input_image = augment(image, alpha_mask)
    keypoints = project_keypoints(keypoints, world_to_camera)
    return input_image, keypoints


class RenderRandomSample(pr.Processor):
    def __init__(self, render, augment, keypoints):
        super(RenderRandomSample, self).__init__()
        self.render, self.augment = render, augment
        self.keypoints = keypoints

    def call(self):
        input_image, keyponts = render_random_sample(
            self.render, self.augment, self.keypoints)


class RandomKeypointsRender(pr.SequentialProcessor):
    def __init__(self, scene, keypoints, image_paths, num_occlusions):
        super(RandomKeypointsRender, self).__init__()
        H, W = scene.viewport_size
        render = pr.Render(scene)
        augment = RandomizeRenderedImage(image_paths, num_occlusions)
        augment.add(pr.NormalizeImage())

        self.add(RenderRandomSample(render, augment, keypoints))
        self.add(pr.SequenceWrapper({0: {'image': [H, W, 3]}},
                                    {1: {'keypoints': [len(keypoints), 3]}}))



import os
import numpy as np
from glob import glob

from pipelines import DrawNormalizedKeypoints
from pipelines import RandomKeypointsRender
from paz.backend.image import show_image
from paz.backend.image import load_image

# filepath = '/home/octavio/.keras/paz/datasets/ycb_models/obj_000001.ply'
# filepath = '/home/octavio/Repositories/solar_panels/solar_panel_02/meshes/obj/base_link.obj'

data_path = '/home/octavio/.keras/paz/datasets/ycb_models/'
class_name = '035_power_drill'
filepath = os.path.join(data_path, class_name, 'textured.obj')
image_shape = (512, 512)
y_fov = 3.14159 / 4.0
distance = [0.3, 0.5]
light = [0.5, 30]
top_only = False
roll = None
shift = None
occlusions = 3
# image_paths = glob('/home/octavio/JPEGImages/*.jpg')
image_paths = glob('/home/octavio/.keras/paz/datasets/voc-backgrounds/*.png')
x_offset = y_offset = z_offset = 0.05
keypoints = np.array([[x_offset, 0.0, 0.0, 1.0],
                      [0.0, y_offset, 0.0, 1.0],
                      [0.0, 0.0, z_offset, 1.0]])

args = (filepath, image_shape, y_fov, distance, light, top_only, roll, shift)
scene = SingleView(*args)
image, alpha_channel, world_to_camera = scene.render()
processor = RandomKeypointsRender(scene, keypoints, image_paths, occlusions)
draw_normalized_keypoints = DrawNormalizedKeypoints(len(keypoints), 10, True)

for arg in range(100):
    sample = processor()
    image = sample['inputs']['image']
    keypoints = sample['labels']['keypoints']
    image = draw_normalized_keypoints(image, keypoints)
    image = (255.0 * image).astype('uint8')
    show_image(image)
