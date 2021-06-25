import numpy as np
import processors as pe
from paz import processors as pr
from paz.pipelines import HaarCascadeFrontalFace
from paz.abstract import SequentialProcessor, Processor


class DetectEigenFaces(Processor):
    def __init__(self, weights_database, parameters, project,
                 mean_face, offsets=[0, 0]):
        super(DetectEigenFaces, self).__init__()
        self.offsets = offsets
        self.colors = parameters['colors']
        self.class_names = parameters['class_names']
        self.croped_images = None
        # detection
        self.detect = HaarCascadeFrontalFace()
        self.square = SequentialProcessor()
        self.square.add(pr.SquareBoxes2D())
        self.square.add(pr.OffsetBoxes2D(offsets))
        self.clip = pr.ClipBoxes2D()
        self.crop = pr.CropBoxes2D()
        self.face_detector = EigenFaceDetector(weights_database, parameters,
                                               project, mean_face)
        # drawing and wrapping
        self.draw = pr.DrawBoxes2D(self.class_names, self.colors, True)
        self.wrap = pr.WrapOutput(['image', 'boxes2D'])

    def call(self, image):
        boxes2D = self.detect(image.copy())['boxes2D']
        boxes2D = self.square(boxes2D)
        boxes2D = self.clip(image, boxes2D)
        self.cropped_images = self.crop(image, boxes2D)
        for cropped_image, box2D in zip(self.cropped_images, boxes2D):
            self.face_detector.store_each_frame(cropped_image)
            self.face_detector()
            box2D.class_name = self.face_detector()
            # box2D.score = np.amax(predictions['scores'])
        image = self.draw(image, boxes2D)
        return self.wrap(image, boxes2D)


class EigenFaceDetector(Processor):
    def __init__(self, weights_data_base, parameters, project, mean_face):
        self.weights_data_base = weights_data_base
        self.calculate_weights = CalculateTestFaceWeights(project, mean_face)
        self.query = QueryFace(parameters)
        super(EigenFaceDetector, self).__init__()

    def store_each_frame(self, test_data):
        self.test_data = test_data

    def call(self):
        test_weight = self.calculate_weights(self.test_data)
        similar_face = self.query(test_weight, self.weights_data_base)
        return similar_face


class QueryFace(Processor):
    def __init__(self, parameters):
        self.norm = np.linalg.norm
        self.norm_order = parameters['norm_order']
        self.threshold = parameters['threshold']
        super(QueryFace).__init__()

    def call(self, test_face_weight, database):
        # you could also get a none
        self.database = database
        weights_difference = []
        for sample in database:
            weight = database[sample].T
            weight_norm = self.norm((weight - test_face_weight),
                                    ord=self.norm_order, axis=1)
            weights_difference.append(np.min(weight_norm))

        if np.min(weights_difference) < self.threshold:
            return None
        else:
            most_similar_face_arg = np.argmin(weights_difference)
        return list(database.keys())[most_similar_face_arg]


class CalculateTestFaceWeights(pr.Processor):
    def __init__(self, project, mean_face, shape=(48, 48)):
        super(CalculateTestFaceWeights, self).__init__()
        self.project = project
        self.mean_face = mean_face
        self.convert_to_gray = pr.ConvertColorSpace(pr.RGB2GRAY)
        self.preprocess = pr.SequentialProcessor()
        self.preprocess.add(pr.ResizeImage(shape))
        self.preprocess.add(pr.ExpandDims(-1))
        self.subtract = pe.SubtractMeanFace()

    def call(self, face):
        if len(face.shape) != 3:
            raise ValueError('input should have shape [H, W, num_channels]')
        if face.shape[-1] == 3:
            face = self.convert_to_gray(face)
        face = self.preprocess(face)
        face = self.subtract(face, self.mean_face)
        weights = self.project(face)
        return weights
