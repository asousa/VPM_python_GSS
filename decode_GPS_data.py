import numpy as np
import pickle
import datetime
import struct
from decode_packets import find_sequence

def decode_GPS_data(data):
    '''
    Author:     Austin Sousa
                austin.sousa@colorado.edu
    Version:    1.0
        Date:   10.15.2019
    Description:
        Decodes GPS data from the Novatel OEM6/7 cards, and returns a dictionary of parameters

    inputs: 
        data: A numpy array with type 'uint8'; the reassembled 
    outputs:
        A Python dictionary
        Each dictionary is a single survey column, and contains the following fields:
            E_data: The electric field data, corresponding to averaged, log-scaled
                    magnitudes of the onboard FFT
            B_data: The magnetic field data, corresponding to averaged, log-scaled
                    magnitudes of the onboard FFT
            GPS:    A dictionary of decoded GPS data, corresponding to the end of
                    the current survey product
    '''
    leap_seconds = 18  # GPS time does not account for leap seconds; as of ~2019, GPS leads UTC by 18 seconds.
    reference_date = datetime.datetime(1980,1,6,0,0,0)
    pos_inds = find_sequence(data,np.array([0xAA, 0x44, 0x12, 0x1C, 0x2A]))
    vel_inds = find_sequence(data,np.array([0xAA, 0x44, 0x12, 0x1C, 0x63]))

    if len(pos_inds)==0 and len(vel_inds)==0:
        print("No GPS logs found")
        return None
    else:
        print(f'found {len(pos_inds)} position logs and {len(vel_inds)} velocity logs')
        # (There should never be more than 1 position and 1 velocity entry)


    # print(['{0:02X}'.format(x) for x in data.astype('int')])

    # See page 47 of the OEM7 Firmware Reference Manual for the header reference indices,
    # and page 443 for the BESTPOS / BESTVEL indices
    header_len = 28;

    out = dict()
    
    if len(pos_inds) > 0:
        x = pos_inds[0]
        H = x + header_len # matches the "H" in the datasheets
        
        # Parameters common to both position and velocity messages:
        time_status = int(data[x + 13])
        receiver_status = struct.unpack('I',data[x + 20: x + 24].tobytes())[0]
        weeknum_pos = 1.0*(data[x + 14] + (data[x + 15] <<8));
        sec_offset_pos =(struct.unpack('I',data[x + 16:x +20].tobytes()))[0]/1000.

        # Parameters in BESTPOS:
        # Number of satellites in view; number of satellites used in solution
        tracked_sats = int(data[H + 64])
        used_sats = int(data[H + 65])

        # Solution status + position type flags:
        sol_stat = struct.unpack('I',data[H:H+4].tobytes())[0]
        pos_type = struct.unpack('I',data[H+4:H+8].tobytes())[0]

        # Lat and Lon are 8-byte doubles; unpack 'em
        lat = struct.unpack('d', data[H+8:H+16].tobytes())[0]
        lon = struct.unpack('d', data[H+16:H+24].tobytes())[0]
        alt = struct.unpack('d', data[H+24:H+32].tobytes())[0]
        
        out['pos'] = [lat, lon, alt]
        out['tracked_sats'] = tracked_sats
        out['used_sats'] = used_sats
        
        # All these fields are in the 'velocity' message as well, and *should* be the same...
        out['time_status'] = time_status
        out['receiver_status'] = receiver_status
        out['weeknum'] = weeknum_pos
        out['sec_offset'] = sec_offset_pos
        out['solution_status'] = sol_stat
        out['solution_type'] = pos_type
    
    if len(vel_inds) > 0:
        x = vel_inds[0]
        H = x + header_len # matches the "H" in the datasheets
        
        # Repeat for the velocity messages:
        time_status = int(data[x + 13])
        receiver_status = struct.unpack('I',data[x + 20: x + 24].tobytes())[0]
        weeknum_vel = 1.0*(data[x + 14] + (data[x + 15] <<8));
        sec_offset_vel =(struct.unpack('I',data[x + 16:x + 20].tobytes()))[0]/1000.

        # Parameters in BESTVEL:
        H = x + header_len

        # Solution status + position type flags:
        sol_stat = struct.unpack('I',data[H:H+4].tobytes())[0]
        vel_type = struct.unpack('I',data[H+4:H+8].tobytes())[0]

        # Latency of velocity measurement, in seconds
        latency = struct.unpack('f',data[H+8:H+12].tobytes())[0]

        # Horizontal and vertical speeds, in meters per second:
        horiz_speed = struct.unpack('d',data[H+16:H+24].tobytes())[0]
        vert_speed  = struct.unpack('d',data[H+32:H+40].tobytes())[0]

        # Direction of motion over the ground WRT True North, in degrees:
        ground_track= struct.unpack('d',data[H+24:H+32].tobytes())[0]

        out['horiz_speed'] = horiz_speed
        out['vert_speed'] = vert_speed
        out['ground_track'] = ground_track
        out['latency'] = latency
        
        if 'weeknum' in out.keys():
            # If we had both a position and velocity message, confirm that the timestamps agree:
            if out['weeknum'] != weeknum_vel:
                print("position / velocity timestamp mismatch")
        else:
            # If we didn't get a position message, use this data
            out['time_status'] = time_status
            out['receiver_status'] = receiver_status
            out['weeknum'] = weeknum_vel
            out['sec_offset'] = sec_offset_vel
            out['solution_status'] = sol_stat
            out['solution_type'] = vel_type
    
    # Python datetime object
    out['time'] = reference_date + datetime.timedelta(weeks=out['weeknum']) + \
                  datetime.timedelta(seconds=out['sec_offset'])
    

    return out