import numpy as np
import matplotlib.pyplot as plt
import pickle
import datetime
from matplotlib.gridspec import GridSpec
import matplotlib.dates as mdates
import scipy.signal
from parula_colormap import parula
import logging
import argparse
import os



def plot_survey_data(S_data, filename="survey_data.pdf", show_plots=False):
    '''
    Author:     Austin Sousa
                austin.sousa@colorado.edu
    Version:    1.0
        Date:   10.14.2019
    Description:
        Plots survey data as PDFs

    inputs: 
        S_data: a list of dictionaries, as returned from decode_survey_data.py
                Each dictionary represents a single column of the survey product.
                A time axis will be constructed using the timestamps within each
                dictionary.
        filename: The filename to save
    outputs:
        saved images; format is defined by the suffix of filename
    '''
    # --------------- Latex Plot Beautification --------------------------
    fig_width = 10 
    fig_height = 8
    fig_size =  [fig_width+1,fig_height+1]
    params = {'backend': 'ps',
              'axes.labelsize': 12,
              'font.size': 12,
              'legend.fontsize': 10,
              'xtick.labelsize': 10,
              'ytick.labelsize': 10,
              'text.usetex': False,
              'figure.figsize': fig_size}
    plt.rcParams.update(params)
    # --------------- Latex Plot Beautification --------------------------


    # Assemble into grids:

    if S_data is None:
        return

    E = []
    B = []
    T = []
    F = np.arange(512)*40/512;
    for S in sorted(S_data, key = lambda f: f['GPS'][0]['timestamp']):
        if S['GPS'] is not None:
            # if S['GPS'][0]['time_status'] != 20:  # Ignore any 
            T.append(S['GPS'][0]['timestamp'])
            # T.append(S['header_timestamp'])
            # print(datetime.datetime.utcfromtimestamp(S['GPS'][0]['timestamp']), S['exp_num'], datetime.datetime.utcfromtimestamp(S['header_timestamp']))
        else:
            T.append(np.nan)

        E.append(S['E_data'])
        B.append(S['B_data'])


    E = np.array(E); B = np.array(B); T = np.array(T);

    # Sort by time vector:
    # (This may cause issues if the GPS card is off, since everything restarts at 1/6/1980 without a lock.
    # The spacecraft timestamp will be accurate enough when bursts are NOT being taken, but things will get
    # weird during a burst, since the data will have sat in the payload SRAM for a bit before receipt.)
    sort_inds = np.argsort(T)
    E = E[sort_inds, :]; B = B[sort_inds, :]; T = T[sort_inds];

    fig = plt.figure()
    gs = GridSpec(2, 2, width_ratios=[20, 1], wspace = 0.05, hspace = 0.05)
    ax1 = fig.add_subplot(gs[0,0])
    ax2 = fig.add_subplot(gs[1,0])
    cbax = fig.add_subplot(gs[:,1])

    # survey_fullscale = 10*np.log10(pow(2,32))

    # # This is how we scaled the data in the Matlab code... I believe this maps the 
    # # VPM values (8-bit log scaled ints) to a log scaled amplitude.
    # E_data = 10*np.log10(pow(2,E_data/8)) - survey_fullscale
    # B_data = 10*np.log10(pow(2,B_data/8)) - survey_fullscale
    # 
    # (This is where we might bring in a real-world calibration factor)
    



    clims = [0,255] #[-80,-40]
    
    t_edges = np.insert(T, 0, T[0] - 26)
    dates = [datetime.datetime.utcfromtimestamp(t) for t in t_edges]
    
    # colormap -- parula is Matlab; also try plt.cm.jet or plt.cm.viridis
    cm = parula();

    # Plot E data
    # p1 = ax1.pcolorfast(E.T, vmin=clims[0], vmax=clims[1])
    p1 = ax1.pcolormesh(dates,F,E.T, vmin=clims[0], vmax=clims[1], shading='flat', cmap = cm);
    # p2 = ax2.pcolorfast(B.T, vmin=clims[0], vmax=clims[1])
    p2 = ax2.pcolormesh(dates,F,B.T, vmin=clims[0], vmax=clims[1], shading='flat', cmap = cm);
    cb = plt.colorbar(p1, cax = cbax)
    cb.set_label('Raw value [0-255]')

    # vertical lines at each edge (kinda nice, but messy for big plots)
    # g1 = ax1.vlines(dates, 0, 40, linewidth=0.2, alpha=0.5, color='w')
    # g2 = ax2.vlines(dates, 0, 40, linewidth=0.2, alpha=0.5, color='w')

    ax1.set_xticklabels([])
    ax1.set_ylim([0,40])
    ax2.set_ylim([0,40])

    formatter = mdates.DateFormatter('%H:%M:%S')
    ax2.xaxis.set_major_formatter(formatter)
    fig.autofmt_xdate()
    ax2.set_xlabel("Time (H:M:S) on \n%s"%datetime.datetime.utcfromtimestamp(T[0]).strftime("%Y-%m-%d"))

    ax1.set_ylabel('E channel\nFrequency [kHz]')
    ax2.set_ylabel('B channel\nFrequency [kHz]')
    
    
    fig.suptitle(f'VPM Survey Data\n {datetime.datetime.utcfromtimestamp(T[0])} -- {datetime.datetime.utcfromtimestamp(T[-1])}')
    # gs.tight_layout(fig)
    
    if show_plots:
        plt.show()
    fig.savefig(filename, bbox_inches='tight')



if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="VPM Ground Support Software")

    parser.add_argument("--in_dir",  required=True, type=str, default = 'input', help="path to directory of .tlm files")
    parser.add_argument("--out_dir", required=False, type=str, default='output', help="path to output directory")

    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument("--debug", dest='debug', action='store_true', help ="Debug mode (extra chatty)")
    g.set_defaults(debug=False)

    args = parser.parse_args()

    #  ----------- Start the logger -------------
    # log_filename = os.path.join(out_root, 'log.txt')
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='[%(name)s]\t%(levelname)s\t%(message)s')
    else:
        logging.basicConfig(level=logging.INFO,  format='[%(name)s]\t%(levelname)s\t%(message)s')
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    # print("plotting survey data...")
    # # Load decoded data:
    # with open("decoded_data.pkl","rb") as f:
    #     d = pickle.load(f)
    # print(d.keys())

    # S_data = d['survey']

    # plot_survey_data(S_data, "survey_data.pdf")