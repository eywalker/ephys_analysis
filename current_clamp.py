import os
import numpy as np
import pandas as pd
import six
from collections import OrderedDict

import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns
from matplotlib import gridspec, animation
from PIL import Image

import allensdk_0_14_2.ephys_features as ft


def load_current_step_add_itrace(abf_file, ihold, istart, istep, startend=None, filetype='abf', channels=[0]):
    '''
    Load current clamp recordings from pClamp .abf files with only voltage traces
    '''
    ch0 = channels[0]
    rec = stfio.read(abf_file)
    assert(rec[ch0].yunits == 'mV')

    data = OrderedDict()
    data['file_id'] = os.path.basename(abf_file).strip('.' + filetype)
    data['file_directory'] = os.path.dirname(abf_file)
    data['record_date'] = rec.datetime.date()
    data['record_time'] = rec.datetime.time()

    data['dt'] = rec.dt / 1000
    data['hz'] = 1./rec.dt * 1000
    data['time_unit'] = 's'

    data['n_channels'] = len(rec)
    data['channel_names'] = [rec[ch0].name, 'Current_simulated']
    data['channel_units'] = [rec[ch0].yunits, 'pA']
    data['n_sweeps'] = len(rec[ch0])
    data['sweep_length'] = len(rec[ch0][0])

    data['t'] = np.arange(0, data['sweep_length']) * data['dt']

    start_idx = ft.find_time_index(data['t'], startend[0])
    end_idx = ft.find_time_index(data['t'], startend[1])
    current = [np.zeros_like(data['t']) + ihold for i in range(data['n_sweeps'])]
    for i in range(data['n_sweeps']):
        current[i][start_idx:end_idx] += istart + istep * i

    data['voltage'] = rec[ch0]
    data['voltage'] = [x.asarray() for x in data['voltage']]
    data['current'] = current

    current_channel = stfio.Channel([stfio.Section(x) for x in current])
    current_channel.yunits = 'pA'
    current_channel.name = 'Current_simulated'
    chlist = [rec[ch0], current_channel]
    rec_with_current = stfio.Recording(chlist)
    rec_with_current.dt = rec.dt
    rec_with_current.xunits = rec.xunits
    rec_with_current.datetime = rec.datetime
    return rec_with_current, data


def plot_current_step(data, fig_height=6, x_scale=3.5, xlim=[0.3,3.2],
                        startend=None, offset=[0.2, 0.4],
                        blue_sweep=None, vlim=[-145,55], ilim=[-95,150],
                        spikes_sweep_id = None, spikes_t = None,
                        bias_current = 0.0, highlight = 'deepskyblue',
                        skip_sweep=1, skip_point=10, save=False):
    '''
    Plot overlayed sweeps in current clamp protocol, with one sweep in blue color
    If detected spikes are provided, also plot detected spikes.
    '''

    plt.style.use('ggplot')

    fig_width = fig_height
    if (spikes_sweep_id is not None) and (spikes_t is not None):
        fig_height *= 4.0/3.0
        n_plots = 3
        height_ratios = [1,3,1]
    else:
        n_plots = 2
        height_ratios = [3,1]

    if startend is not None:
        assert(type(startend) is list and len(startend) == 2)
        start = startend[0] - offset[0]
        end = startend[1] + offset[1]
        xlim = [start, end]
        length = end - start
        figsize = (length * x_scale * fig_width / 6., fig_height)
    else:
        figsize = (fig_width, fig_height)

    fig = plt.figure(figsize=figsize)
    fig.patch.set_alpha(0.1)
    gs = gridspec.GridSpec(n_plots, 1, height_ratios=height_ratios)

    axes = [plt.subplot(gs[x]) for x in range(n_plots)]

    indices = [x for x in range(data['n_sweeps']) if x % skip_sweep ==0 or x == data['n_sweeps']-1]
    # print(indices)

    if blue_sweep is not None:
        assert(type(blue_sweep) is int)
        if not blue_sweep in indices:
            indices.append(blue_sweep)
    else:
        blue_sweep = indices[-2]

    for i in indices:
        if i == blue_sweep or i == data['n_sweeps'] + blue_sweep:
            color = highlight
            lw=1.25
            size=8
            alpha=1
        else:
            color = 'gray'
            lw=0.2
            size=3
            alpha=0.6

        axes[-2].plot(data['t'][::skip_point], data['voltage'][i][::skip_point], color=color, lw=lw, alpha=alpha)

        axes[-2].set_ylim(vlim)
        axes[-2].set_ylabel('Membrane Voltage (mV)')
        axes[-2].set_xticklabels([])

        axes[-1].plot(data['t'][::skip_point], data['current'][i][::skip_point] - bias_current, color=color, lw=lw, alpha=alpha)
        axes[-1].set_ylim(ilim)
        axes[-1].set_ylabel('Current (pA)')
        axes[-1].set_xlabel('Time (s)')

        if n_plots == 3:
            spikes = spikes_t[spikes_sweep_id==i]
            axes[0].scatter(spikes, np.ones_like(spikes) * i, marker='o', s=size, c=color, alpha=alpha)
            axes[0].set_ylim([1, data['n_sweeps']])
            axes[0].set_xticklabels([])
            # axes[0].set_ylabel('Sweeps')


    for ax in axes:
        ax.set_xlim(xlim)
        ax.patch.set_alpha(0.2)

    plt.tight_layout()
    if save is True:
        plt.savefig(os.path.join(data['file_directory'], data['file_id']) + '.png', dpi=300)
        plt.savefig(os.path.join(data['file_directory'], data['file_id']) + '.svg')
        plt.savefig(os.path.join(data['file_directory'], data['file_id']) + '.pdf')

    return fig


def animate_current_step(data, fig_height=6, x_scale=3.5, xlim=[0.3,3.2],
                        startend=None, offset=[0.2, 0.4],
                        blue_sweep=None, vlim=[-155,55], ilim=[-95,150],
                        spikes_sweep_id = None, spikes_t = None,
                        bias_current = 0.0, highlight = 'deepskyblue',
                        skip_point=10, save=False, save_filepath=None):
    '''
    Make animated GIF containing all the sweeps in current clamp protocol.
    If detected spikes are provided, also plot detected spikes.
    '''
    fig_width = fig_height
    if (spikes_sweep_id is not None) and (spikes_t is not None):
        fig_height *= 4.0/3.0
        n_plots = 3
        height_ratios = [1,3,1]
    else:
        n_plots = 2
        height_ratios = [3,1]


    def init_animation():
        animate(-1)

    def animate(j):
        plt.style.use('ggplot')

        gs = gridspec.GridSpec(n_plots, 1, height_ratios=height_ratios)
        axes = [plt.subplot(gs[x]) for x in range(n_plots)]

        for i in range(data['n_sweeps']):
            if i == j:
                color = highlight
                lw=1.5
                size=12
                alpha=1
            else:
                color = 'gray'
                lw=0.2
                size=4
                alpha=0.6

            axes[-2].plot(data['t'][::skip_point], data['voltage'][i][::skip_point], color=color, lw=lw, alpha=alpha)

            axes[-2].set_ylim(vlim)
            axes[-2].set_ylabel('Membrane Voltage (mV)')
            axes[-2].set_xticklabels([])
            axes[-1].plot(data['t'][::skip_point], data['current'][i][::skip_point] - bias_current, color=color, lw=lw, alpha=alpha)
            axes[-1].set_ylim(ilim)
            axes[-1].set_ylabel('Current (pA)')
            axes[-1].set_xlabel('Time (s)')
            if n_plots == 3:
                spikes = spikes_t[spikes_sweep_id==i]
                axes[0].scatter(spikes, np.ones_like(spikes) * i, marker='o', s=size, c=color, alpha=alpha)
                axes[0].set_ylim([1, data['n_sweeps']])
                axes[0].set_xticklabels([])
                # axes[0].set_ylabel('Sweeps')

        for ax in axes:
            ax.set_xlim(xlim)
            ax.patch.set_alpha(0.2)

        plt.tight_layout()

    if startend is not None:
        assert(type(startend) is list and len(startend) == 2)
        start = startend[0] - offset[0]
        end = startend[1] + offset[1]
        xlim = [start, end]
        length = end - start
        figsize = (length * x_scale * fig_width / 6., fig_height)
    else:
        figsize = (fig_width, fig_height)
    fig = plt.figure(figsize=figsize)

    anim = animation.FuncAnimation(fig, animate, init_func=init_animation, frames=data['n_sweeps'])
    if save:
        if save_filepath is not None:
            # use default dpi=100. Setting other dpi values will produce wierd-looking plots.
            anim.save(save_filepath, writer='imagemagick', fps=2.5)
        else:
            anim.save(os.path.join(data['file_directory'], data['file_id']) + '.gif', writer='imagemagick', fps=2.5)
    return fig



def plot_fi_curve(stim_amp, firing_rate, save_filepath = None):
    '''
    Plot F-I curve
    '''
    mpl.rcParams.update(mpl.rcParamsDefault)
    fig, ax = plt.subplots(1,1,figsize=(4,4))
    ax.plot(stim_amp, firing_rate, marker='o', linewidth=1.5, markersize=8)
    fig.gca().spines['right'].set_visible(False)
    fig.gca().spines['top'].set_visible(False)
    ax.set_ylabel('Spikes per second', fontsize=14)
    ax.set_xlabel('Current (pA)', fontsize=14)
    fig.tight_layout()
    if save_filepath is not None:
        fig.savefig(save_filepath, dpi=300)
    return fig


def plot_first_spike(data, features, time_zero='threshold',
                    window=None, vlim=[-80, 50], color=sns.color_palette("muted")[2],
                    save_filepath = None):
    '''
    Plot the first action potential. Time window is something like:
    Inputs
    -----
    data: raw data of sweeps loaded by load_current_step()
    features: dictionary from extract_istep_features()
    time_zero: whether to use threshold or peak time
    window: time range in ms. such as [t-10, t+40] ms

    Returns
    -------
    figure object
    '''
    assert(time_zero in ['threshold', 'peak'])
    if time_zero == 'threshold':
        t0 = features['spikes_threshold_t'][0]
        if window is None:
            window = [-10, 40]
    elif time_zero == 'peak':
        t0 = features['spikes_peak_t'][0]
        if window is None:
            window = [-15, 35]

    ap_window = [t0 + x * 0.001 for x in window]
    start, end = [ft.find_time_index(data['t'], x) for x in ap_window]
    t = (data['t'][start:end] - data['t'][start]) * 1000 + window[0]
    v = data['voltage'][features['rheobase_index']][start:end]

    mpl.rcParams.update(mpl.rcParamsDefault)
    fig, ax = plt.subplots(1,1,figsize=(4,4))
    ax.plot(t, v, color=color)

    threshold_time = (features['spikes_threshold_t'][0] - t0) * 1000
    ax.hlines(features['ap_threshold'], window[0], threshold_time,
                linestyles='dotted', color='grey')

    ax.set_ylim(vlim)
    fig.gca().spines['right'].set_visible(False)
    fig.gca().spines['top'].set_visible(False)
    ax.set_ylabel('Voltage (mV)', fontsize=14)
    ax.set_xlabel('Time (ms)', fontsize=14)
    fig.tight_layout()

    if save_filepath is not None:
        fig.savefig(save_filepath, dpi=300)
    return fig


def plot_phase_plane(data, features, filter=None, window=[-50, 200],
                        vlim=[-85, 50], dvdtlim=[-80, 320],
                        color=sns.color_palette("muted")[1],
                        save_filepath=None):
    t0 = features['spikes_threshold_t'][0]
    ap_window = [t0 + x * 0.001 for x in window]

    if len(features['spikes_sweep_id']) > 1 and \
        features['spikes_sweep_id'][1] == features['spikes_sweep_id'][0]:
            ap_window[1] = min(ap_window[1], features['spikes_threshold_t'][1])

    start, end = [ft.find_time_index(data['t'], x) for x in ap_window]
    t = (data['t'][start:end] - data['t'][start]) * 1000 + window[0]
    v = data['voltage'][features['rheobase_index']][start:end]
    dvdt = ft.calculate_dvdt(v, t, filter=filter) * 1000

    mpl.rcParams.update(mpl.rcParamsDefault)
    fig, ax = plt.subplots(1,1,figsize=(4, 4))
    ax.plot(v[0:-1], dvdt, color=color)

    ax.set_xlim(vlim)
    ax.set_ylim(dvdtlim)
    fig.gca().spines['right'].set_visible(False)
    fig.gca().spines['top'].set_visible(False)
    ax.set_xlabel('Voltage (mV)', fontsize=14)
    ax.set_ylabel('dV/dt (V/s)', fontsize=14)
    fig.tight_layout()

    if save_filepath is not None:
        fig.savefig(save_filepath, dpi=300)
    return fig


def combine_vertical(images, scale = 1):
    # combine multiple PIL images
    # roughtly same width
    height = sum([x.size[1] for x in images])
    width = max([x.size[0] for x in images])
    combined = Image.new('RGB', (width, height), (255,255,255))

    y_offset = 0
    for im in images:
        if len(im.split()) > 3:
            combined.paste(im, (0, y_offset), mask=im.split()[3])
        else:
            combined.paste(im, (0, y_offset))
        y_offset += im.size[1]
    if scale != 1:
        combined = combined.resize([int(x * scale) for x in combined.size], resample=Image.BICUBIC)
    return combined


def combine_horizontal(images, scale = 1, same_size = False):
    # combine multiple PIL images
    if not same_size:
        min_height = min([x.size[1] for x in images])
        min_i = np.argmin([x.size[1] for x in images])
        scales = [min_height / x.size[1] for i, x in enumerate(images)]
        resized = images.copy()

        for i in range(len(resized)):
            if i != min_i:
                resized[i] = resized[i].resize([int(x * scales[i]) for x in resized[i].size], resample=Image.BICUBIC)
    else:
        resized = images

    width = sum([x.size[0] for x in resized])
    height = max([x.size[1] for x in resized])
    combined = Image.new('RGB', (width, height), (255,255,255))

    x_offset = 0
    for im in resized:
        if len(im.split()) > 3:
            combined.paste(im, (x_offset,0), mask=im.split()[3])
        else:
            combined.paste(im, (x_offset,0))
        x_offset += im.size[0]
    if scale != 1:
        combined = combined.resize([int(x * scale) for x in combined.size], resample=Image.BICUBIC)

    return combined
