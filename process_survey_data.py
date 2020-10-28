import sys
import os
import datetime
import pickle
import gzip
from scipy.io import savemat
from configparser import ConfigParser
import numpy as np
from file_handlers import load_packets_from_tree
from file_handlers import read_survey_XML, write_survey_XML
from data_handlers import decode_packets_TLM, decode_packets_CSV, decode_survey_data, unique_entries
from db_handlers import get_packets_within_range, get_time_range_for_updated_packets
from log_handlers import get_last_access_time, log_access_time
import logging
from compute_ground_track import fill_missing_GPS_entries



def get_timestamp(x):
    logger = logging.getLogger('get_timestamp')
    try:
        ts = x['GPS'][0]['timestamp']
    except:
        logger.info("entry is missing GPS data")
        ts = x['header_timestamp']
    return ts


# Sift out packets with GPS issues (no lock, or not present)
def valid_GPS_mask(s):
    try:
        g = s['GPS'][0]
        # Time status messages:
        # 20 -- UNKNOWN
        # 60 -- APPROXIMATE
        # 80 -- COARSEADJUSTING
        # 100 -- COARSE
        # 120 -- COARSESTEERING
        # 130 -- FREEWHEELING
        # 140 -- FINEADJUSTING
        # 160 -- FINE
        # 170 -- FINEBACKUPSTEERING
        # 180 -- FINESTEERING
        # 200 -- SATTIME
        stat = g['time_status']
        return (stat > 20)
    except:
#         print("entry is missing GPS data")
        return False
    
    return temp

def save_survey_to_file_tree(S_data, out_root, file_types=['xml']):
    logger = logging.getLogger('save_survey_to_file_tree')



    # -------------------- Filter out invalid entries -----------------------------
    S_valid   = list(filter(lambda x: valid_GPS_mask(x), S_data))
    S_invalid = list(filter(lambda x: not valid_GPS_mask(x), S_data))


    # ---------------- Quantize timestamps into range of days -----------------------------
    dates = [datetime.datetime.fromtimestamp(x['GPS'][0]['timestamp'],
                             tz=datetime.timezone.utc) for x in S_valid]

    days_to_do = np.unique([x.replace(hour=0, minute=0, second=0) for x in dates])

    logger.info(f"Days to do: {[x.strftime('%Y-%m-%d') for x in days_to_do]}")

    logger.info(f'{len(S_data)} total survey products: {len(S_valid)} valid, {len(S_invalid)} rejected')



    for d in days_to_do:
        logger.info(f'doing {d}')
        t1 = d.timestamp()
        t2 = (d + datetime.timedelta(days=1)).timestamp()
        S_filt = list(filter(lambda x: (get_timestamp(x) >= t1) and (get_timestamp(x) < t2), S_data))


        if S_filt:
            outpath = os.path.join(out_root,'xml',f'{d.year}', '{:02d}'.format(d.month))
            fname = f"VPM_survey_data_{d.strftime('%Y-%m-%d')}.xml"
            # Check for previous file
            outfile = os.path.join(outpath, fname)

            # Here we're using the XML files as the master record. Load previous
            # entries and merge with the new ones; remove duplicates.
            if not os.path.exists(outpath):
                os.makedirs(outpath)
            if os.path.exists(outfile):
                logger.info('file exists! Loading previous entries')

                S_previous = read_survey_XML(outfile)
                logger.info(f'Joining {len(S_previous)} entries with current {len(S_filt)}')

                S_filt.extend(S_previous)
                len_pre_filt = len(S_filt)
                S_filt = unique_entries(S_filt)
                logger.info(f'rejecting {len_pre_filt - len(S_filt)} duplicate entries')

            logger.info(f'saving {len(S_filt)} survey entries')
            S_filt = sorted(S_filt, key=lambda x: get_timestamp(x))

            # Can save xml, matlab, or pickle file types:
            for ftype in file_types:
                outpath = os.path.join(out_root,ftype,f'{d.year}', '{:02d}'.format(d.month))
                fname = f"VPM_survey_data_{d.strftime('%Y-%m-%d')}.{ftype}"
                outfile = os.path.join(outpath, fname)
                if not os.path.exists(outpath):
                    os.makedirs(outpath)

                if ftype =='xml':
                    # Write XML file
                    write_survey_XML(S_filt, outfile)

                if ftype=='mat':
                    # Write MAT file
                    savemat(outfile, {'survey_data' : S_filt})

                if ftype=='pkl':
                    # Write pickle file
                    with open(outfile,'wb') as file:
                        pickle.dump(S_filt, file)                    

    # ---------------- Cache invalid packets -----------------------------

    if S_invalid:
        invalid_xml_file = os.path.join(out_root,'xml','invalid_entries.xml')

        if os.path.exists(invalid_xml_file):
            logger.info('file exists! Loading previous entries')

            S_previous = read_survey_XML(invalid_xml_file)
            logger.info(f'Joining {len(S_previous)} entries with current {len(S_invalid)}')
            S_invalid.extend(S_previous)
            len_pre_filt = len(S_invalid)
            S_invalid = unique_entries(S_invalid)
            logger.info(f'rejecting {len_pre_filt - len(S_invalid)} duplicate entries')

        logger.info(f'saving {len(S_invalid)} rejected survey entries')
        S_invalid = sorted(S_invalid, key=lambda x: get_timestamp(x))

        for ftype in file_types:
            invalid_file = os.path.join(out_root,ftype,f'invalid_entries.{ftype}')

            if ftype=='xml':
                write_survey_XML(S_invalid, invalid_file)

            if ftype=='mat':
                savemat(invalid_file, {'survey_data': S_invalid})

            if ftype=='pkl':
                with open(outfile,'wb') as file:
                    pickle.dump(S_invalid, file)


def main():
    # -------- Load configuration file --------
    config = ConfigParser()
    fp = open('GSS_settings.conf')
    config.read_file(fp)
    fp.close()

    # -------- Configure logger ---------
    logfile = config['logging']['log_file']
    logging.basicConfig(level=eval(f"logging.{config['logging']['log_level']}"),
             filename = logfile, 
             format='[%(asctime)s]\t%(module)s.%(name)s\t%(levelname)s\t%(message)s',
             datefmt='%Y-%m-%d %H:%M:%S')
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    np.seterr(divide='ignore')

    packet_db = config['db_locations']['packet_db_file']
    out_root = config['db_locations']['survey_tree_root']
    access_log = config['logging']['access_log']
    
    file_types = config['survey_config']['file_types']
    file_types = [x.strip() for x in file_types.split(',')]
    S_data = []

    fill_GPS = int(config['survey_config']['fill_missing_GPS']) > 0

    # Get the last time we ran this script:
    last_timestamp = get_last_access_time(access_log,'process_survey_data')
    last_time = datetime.datetime.utcfromtimestamp(last_timestamp)
    logging.info(f'Last run time: {last_time} UTC')

    # Get the range of header timestamps corresponding to
    # packets added after the last time we ran:
    
    tsmin, tsmax = get_time_range_for_updated_packets(packet_db, last_timestamp)

    if (not tsmin) or (not tsmax):
        logging.info('No new data to process')
    else:    
        logging.info(f'Header timestamps range from {datetime.datetime.utcfromtimestamp(tsmin)} to {datetime.datetime.utcfromtimestamp(tsmax)}')
        # Add in some extra margin, in case the new minimum is in the middle of a burst
        tmin = datetime.datetime.utcfromtimestamp(tsmin) - datetime.timedelta(hours=2)
        tmax = datetime.datetime.utcfromtimestamp(tsmax) + datetime.timedelta(hours=2)
        logging.info(f'Loading packets with header timestamps {tmin} to {tmax}')

        # ---------------- Load packets --------------------
        # this version from a file tree (.pklz files)
        # packets = load_packets_from_tree(in_root)

        # this version from the database!
        packets = get_packets_within_range(packet_db, dtype='S', t1=tmin, t2 = tmax)


        # -------------------- Decode survey data from packets --------------------
        if packets:
            from_packets, unused = decode_survey_data(packets, separation_time=4.5)
            logging.info(f'Decoded {len(from_packets)} survey products, ({len(unused)}) unused packets remaining')
            S_data.extend(from_packets)

        if S_data:

            # Replace any missing GPS positions with TLE-propagated data
            if fill_GPS:
                fill_missing_GPS_entries([x['GPS'][0] for x in S_data])

            save_survey_to_file_tree(S_data, out_root, file_types=file_types)
    
    log_access_time(access_log, 'process_survey_data')

if __name__ == "__main__":
    main()