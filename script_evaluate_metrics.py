#!/usr/bin/python

"""

This script computes several SLAM metrics.
It is based on the TUM scripts

"""

import sys
import numpy as np
import argparse
import utils
import plot_utils
import slam_metrics
import SE3UncertaintyLib as SE3Lib

if __name__=="__main__":
    # parse command line
    parser = argparse.ArgumentParser(description='''
    This script computes different error metrics for SLAM from the ground truth trajectory and the estimated trajectory.
    ''')
    # Add argument options
    parser.add_argument('gt_file', help='ground truth trajectory (format: timestamp tx ty tz qx qy qz qw)')
    parser.add_argument('est_file', help='estimated trajectory (format: timestamp tx ty tz qx qy qz qw)')
    parser.add_argument('--offset', help='time offset added to the timestamps of the second file (default: 0.0)',default=0.0)
    parser.add_argument('--offset_initial', help='time offset to start the sequence analysis (default: 0.0)',default=0.0)
    parser.add_argument('--scale', help='scaling factor for the second trajectory (default: 1.0)',default=1.0)
    parser.add_argument('--max_pairs', help='maximum number of pose comparisons (default: 10000, set to zero to disable downsampling)', default=10000)
    parser.add_argument('--max_difference', help='maximally allowed time difference for matching entries (default: 0.02)',default=0.02)
    parser.add_argument('--fixed_delta', help='only consider pose pairs that have a distance of delta delta_unit (e.g., for evaluating the drift per second/meter/radian)', action='store_true')
    parser.add_argument('--delta', help='delta for evaluation (default: 1.0)',default=1.0)
    parser.add_argument('--delta_unit', help='unit of delta (options: \'s\' for seconds, \'m\' for meters, \'rad\' for radians, \'f\' for frames; default: \'m\')',default='m')
    parser.add_argument('--alignment', help='type of trajectory alignment (options: \'first\' for first pose, \'manifold\' for manifold, \'horn\' for Horn\'s method; default: \'horn\')',default='horn')
    parser.add_argument('--plot_lang', help='language used to show the plots; default: \'EN\')',default='EN')
    parser.add_argument('--plot_format', help='format to export the plots; default: \'pdf\')',default='pdf')

    parser.add_argument('--ate_manifold', help='computes the error using ATE on the manifold', action='store_true')
    parser.add_argument('--rpe', help='computes RPE', action='store_true')
    parser.add_argument('--ddt', help='computes DDT', action='store_true')
    parser.add_argument('--automatic_scale', help='ATE_Horn computes the absolute scale using the mod by Raul Mur', action='store_true')
    parser.add_argument('--show_plots', help='shows the trajectory plots', action='store_true')
    parser.add_argument('--no_metrics', help='not computes the metrics, used for plotting test only', action='store_true')
    parser.add_argument('--verbose', help='print all evaluation data (otherwise, only the RMSE absolute will be printed)', action='store_true')
    parser.add_argument('--ignore_timestamp_match', help='ignores the timestamp to associate the sequences', action='store_true')
    parser.add_argument('--recommended_offset', help='ignores the given offset and uses the recommended offset obtained from the sequences', action='store_true')

    #parser.add_argument('--save', help='save aligned second trajectory to disk (format: stamp2 x2 y2 z2)')
    #parser.add_argument('--save_associations', help='save associated first and aligned second trajectory to disk (format: stamp1 x1 y1 z1 stamp2 x2 y2 z2)')
    #parser.add_argument('--plot', help='plot the first and the aligned second trajectory to an image (format: png)')
    args = parser.parse_args()

    # configure the plotting stuff
    plot_utils.set_language(lang=args.plot_lang)
    plot_utils.set_file_extension(ext=args.plot_format)

    # read files in TUM format or TUM modified format (with covariances)
    gt_dict  = utils.read_file_dict(args.gt_file)
    est_dict = utils.read_file_dict(args.est_file)

    # check file format
    gt_format = utils.check_valid_pose_format(gt_dict)
    est_format = utils.check_valid_pose_format(est_dict)

    # generate poses
    if gt_format == 'tum_cov':
        gt_poses, gt_cov = utils.convert_file_dict_to_pose_dict(gt_dict, file_format=gt_format)
        est_poses, est_cov = utils.convert_file_dict_to_pose_dict(est_dict, file_format=est_format)
    else:
        gt_poses  = utils.convert_file_dict_to_pose_dict(gt_dict, file_format=gt_format)
        est_poses = utils.convert_file_dict_to_pose_dict(est_dict, file_format=est_format)

    #for key in est_poses:
    #    print(est_poses[key][0:3,3])

    # apply scale
    scale = float(args.scale)
    if args.automatic_scale:
        scale = utils.compute_scale_from_trajectories(gt_poses, est_poses)
    print('Using scale: %f' % scale)
    gt_poses  = utils.scale_dict(gt_poses, scale_factor=1)
    est_poses = utils.scale_dict(est_poses, scale_factor=scale)
    if gt_format == 'tum_cov':
        gt_cov_   = utils.scale_dict(gt_cov, scale_factor=1, is_cov=True)
        est_cov   = utils.scale_dict(est_cov, scale_factor=scale, is_cov=True)

    # associate sequences according to timestamps
    if not args.ignore_timestamp_match:
        gt_poses, est_poses = utils.associate_and_filter(gt_poses, est_poses, offset=float(args.offset), max_difference=float(args.max_difference), offset_initial=float(args.offset_initial), recommended_offset=args.recommended_offset)
        if gt_format == 'tum_cov':
            gt_cov, est_cov = utils.associate_and_filter(gt_cov, est_cov, offset=float(args.offset), max_difference=float(args.max_difference), offset_initial=float(args.offset_initial), recommended_offset=args.recommended_offset)

    # align poses
    if args.alignment == 'manifold':
        if gt_format == 'tum_cov':
            gt_poses_align, est_poses_align, T_align_man = utils.align_trajectories_manifold(gt_poses, est_poses, cov_est=est_cov, align_gt=False)
        else:
            gt_poses_align, est_poses_align, T_align_man = utils.align_trajectories_manifold(gt_poses, est_poses, align_gt=False)
    elif args.alignment == 'horn':
        gt_poses_align, est_poses_align, T_align_horn = utils.align_trajectories_horn(gt_poses, est_poses, align_gt=False)
    elif args.alignment == 'first':
        gt_poses_align, est_poses_align = utils.align_trajectories_to_first(gt_poses, est_poses)


    if(not args.no_metrics):
        # Compute metrics
        # ATE (Absolute trajectory error)
        print('\nATE - Horn')
        ate_horn_error = slam_metrics.ATE_Horn(gt_poses_align, est_poses_align)
        slam_metrics.compute_statistics(np.linalg.norm(ate_horn_error, axis=0), verbose=args.verbose)

        print('\nATE - Horn - X')
        ate_horn_error = slam_metrics.ATE_Horn(gt_poses_align, est_poses_align, axes='X')
        slam_metrics.compute_statistics(np.linalg.norm(ate_horn_error, axis=0), verbose=args.verbose)

        print('\nATE - Horn - Y')
        ate_horn_error = slam_metrics.ATE_Horn(gt_poses_align, est_poses_align, axes='Y')
        slam_metrics.compute_statistics(np.linalg.norm(ate_horn_error, axis=0), verbose=args.verbose)

        print('\nATE - Horn - Z')
        ate_horn_error = slam_metrics.ATE_Horn(gt_poses_align, est_poses_align, axes='Z')
        slam_metrics.compute_statistics(np.linalg.norm(ate_horn_error, axis=0), verbose=args.verbose)



        # ATE (Absolute trajectory error, SE(3))
        if(args.ate_manifold):
            print('\nATE - Manifold')
            ate_se3_error = slam_metrics.ATE_SE3(gt_poses_align,
                                                 est_poses_align,
                                                 offset=float(args.offset),
                                                 max_difference=float(args.max_difference))
            slam_metrics.compute_statistics(np.linalg.norm(ate_se3_error[0:3,:], axis=0), variable='Translational', verbose=args.verbose)
            slam_metrics.compute_statistics(np.linalg.norm(ate_se3_error[3:6,:], axis=0), variable='Rotational', verbose=args.verbose)

        # RPE (Relative Pose Error)
        if(args.rpe):
            print('\nRPE - %s [%s]' % (args.delta, args.delta_unit))
            rpe_error, rpe_trans_error, rpe_rot_error, rpe_distance = slam_metrics.RPE(gt_poses_align,
                                                                       est_poses_align,
                                                                       param_max_pairs=int(args.max_pairs),
                                                                       param_fixed_delta=args.fixed_delta,
                                                                       param_delta=float(args.delta),
                                                                       param_delta_unit=args.delta_unit,
                                                                       param_offset=float(args.offset))

            slam_metrics.compute_statistics(np.linalg.norm(rpe_error[0:3,:], axis=0), variable='Translational', verbose=args.verbose)
            slam_metrics.compute_statistics(np.linalg.norm(rpe_error[3:6,:], axis=0), variable='Rotational', verbose=args.verbose)

        # DDT (Drift per distance)
        if(args.ddt):
            print('\nDDT')
            ddt = np.divide(rpe_error, rpe_distance)
            slam_metrics.compute_statistics(np.linalg.norm(ddt[0:3,:], axis=0), variable='Translational', verbose=args.verbose)
            slam_metrics.compute_statistics(np.linalg.norm(ddt[3:6,:], axis=0), variable='Rotational', verbose=args.verbose)

    if(args.show_plots):
        gt_data = gt_poses_align
        est_data = est_poses_align

        gt_stamps = list(gt_data.keys())
        gt_stamps.sort()
        est_stamps = list(est_data.keys())
        est_stamps.sort()

        #gt_t0 = gt_stamps[0]
        #est_t0 = est_stamps[0]

        #gt_T0 = np.linalg.inv(gt_data[gt_t0])
        #est_T0 = np.linalg.inv(est_data[est_t0])

        #gt_data  = dict( [(a, np.dot(gt_T0, gt_data[a])) for a in gt_data])
        #est_data  = dict( [(a, np.dot(est_T0, est_data[a])) for a in est_data])

        gt_xyz  = np.matrix([gt_data[a][0:3,3] for a in gt_data]).transpose()
        est_xyz  = np.matrix([est_data[a][0:3,3] for a in est_data]).transpose()

        gt_angles   = np.matrix([utils.rotm_to_rpy(gt_data[a][0:3,0:3]) for a in gt_data]).transpose()
        est_angles  = np.matrix([utils.rotm_to_rpy(est_data[a][0:3,0:3]) for a in est_data]).transpose()

        plot_utils.plot_2d_traj_xyz(gt_stamps, gt_xyz, est_stamps, est_xyz, save_fig=True)
        #plot_utils.plot_2d_traj_xyz(gt_stamps, gt_angles, est_stamps, est_angles)
        #plot_utils.plot_3d_xyz(gt_xyz, est_xyz)
        #plot_utils.plot_3d_xyz_with_cov(gt_data, est_data, gt_cov=gt_cov, est_cov=est_cov)
        #plot_utils.plot_3d_xyz(gt_xyz, est_xyz)
