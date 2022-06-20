import numpy as np
from paz.datasets import MANOHandJoints
from paz.backend.groups import to_affine_matrix
from paz.backend.groups import rotation_matrix_to_compact_axis_angle


def calculate_relative_angle(absolute_rotation, links_origin_transform,
                             parents=MANOHandJoints.parents):
    """Calculate the realtive joint rotation for the minimal hand joints.

    # Arguments
        absolute_angles : Array [num_joints, 4].
        Absolute joint angle rotation for the minimal hand joints in
        Euler representation.

    # Returns
        relative_angles: Array [num_joints, 3].
        Relative joint rotation of the minimal hand joints in compact
        axis angle representation.
    """
    relative_angles = np.zeros((len(absolute_rotation), 3))
    for angle_arg in range(len(absolute_rotation)):
        rotation = absolute_rotation[angle_arg]
        transform = to_affine_matrix(rotation, np.array([0, 0, 0]))
        inverted_transform = np.linalg.inv(transform)
        parent_arg = parents[angle_arg]
        if parent_arg is not None:
            link_transform = links_origin_transform[parent_arg]
            child_to_parent_transform = np.dot(inverted_transform,
                                               link_transform)
            child_to_parent_rotation = child_to_parent_transform[:3, :3]
            parent_to_child_rotation = np.linalg.inv(child_to_parent_rotation)
            parent_to_child_rotation = rotation_matrix_to_compact_axis_angle(
                parent_to_child_rotation)
            relative_angles[angle_arg] = parent_to_child_rotation
    return relative_angles


def reorder_relative_angles(relative_angles, root_angle, children):
    """Reorder the relative angles according to the kinematic chain

    # Arguments
        relative_angles: Array
        root_angle: Array. root joint angle for the minimal hand
        children: List, Indexes of the children in the kinematic chain.

    # Returns
        angles: Array. Reordered relative angles
    """
    if root_angle.shape == (3, 3):
        root_angle = rotation_matrix_to_compact_axis_angle(root_angle)
    angles = np.zeros(shape=(len(relative_angles), 3))
    angles[0] = root_angle
    # angles[1:len(children), :] = relative_angles[children[1:], :]
    angles[children[1:], :] = relative_angles[children[1:], :]
    return angles


def change_link_order(joints, config1_labels, config2_labels):
    """Map data from config1_labels to config2_labels.

    # Arguments
        joints: Array
        config1_labels: joint configuration of the joints
        config2_labels: output joint configuration of the joints

    # Returns
        Array: joints maped to the config2_labels
    """
    mapped_joints = []
    for joint_arg in range(len(config2_labels)):
        joint_label = config2_labels[joint_arg]
        joint_index_in_config1_labels = config1_labels.index(joint_label)
        joint_in_config1_labels = joints[joint_index_in_config1_labels]
        mapped_joints.append(joint_in_config1_labels)
    mapped_joints = np.stack(mapped_joints, 0)
    return mapped_joints


def is_hand_open(relative_angles, joint_order, thresh):
    """Check is the hand is open by calculating relative pip joint angle norm.

       [(theta * ex), (theta * ey), (theta * ez)] = compact axis angle
       ex, ey, ez = normalized_axis
       theta = angle
                  _______________________________________________
       norm =    / (theta**2) * [(ex**2) + (ey**2) + (ez**2)]
               \/

       => norm is directly proportional to the theta if axis is notmalized.
          If hand is open the relative angle of the pip joint will be less as
          compared to for the closed hand.

    # Arguments
        relative_angle: Array
        joint_order: Dictionary for the joint order
        thresh: Float. Threshold value for theta

    # Returns
        Boolean: Hand is open or closed.
    """
    relative_angles = np.asarray(relative_angles, dtype=np.float32)
    theta_i = np.linalg.norm(relative_angles[joint_order['index_finger_pip']])
    theta_m = np.linalg.norm(relative_angles[joint_order['middle_finger_pip']])
    theta_r = np.linalg.norm(relative_angles[joint_order['ring_finger_pip']])
    theta_p = np.linalg.norm(relative_angles[joint_order['pinky_pip']])
    if theta_i > thresh and theta_m > thresh and \
            theta_r > thresh and theta_p > thresh:
        return False
    else:
        return True
