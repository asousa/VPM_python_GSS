import numpy as np
import os
import ephem
import datetime
import json
import bisect


# Helper functions
class Satellite(object):

    def __init__(self, tle1, tle2, name): 
        self.tle_rec = None
        self.cur_TLE = ['', '']
        self.curr_time = None
        self.name = None
        self.coords = None    # Long, Lat! XY on a map, but isn't pleasant to say out loud.

        self.update_TLEs(tle1, tle2, name)


    def compute(self,plotdate):
        self.tle_rec.compute(plotdate)
        self.curr_time = plotdate
        self.coords = [(180.0/np.pi)*self.tle_rec.sublong, (180.0/np.pi)*self.tle_rec.sublat]

    def coords_at(self,plotdate):
        ''' Get full coordinates for orbit '''
        self.compute(plotdate)
        return self.coords
    
    def coords_3d_at(self,plotdate):
        ''' Get full coordinates for orbit '''
        self.compute(plotdate)
        self.coords = [(180.0/np.pi)*self.tle_rec.sublong, (180.0/np.pi)*self.tle_rec.sublat, self.tle_rec.elevation]

        return self.coords

    def update_TLEs(self, tle1, tle2, name):

        if (tle1 != self.cur_TLE[0]) or (tle2 != self.cur_TLE[1]) or (self.name != name):
            self.tle_rec = ephem.readtle(name, tle1, tle2)
            self.cur_TLE = [tle1, tle2]
            self.name = name

            print('updated TLE')



def compute_ground_track(TLE, t1, t2, tstep = datetime.timedelta(seconds=30)):
    '''
    plot the ground track of a satellite, as specified by its TLE, between times
    t1 and t2 
    '''
    
    assert (t2 > t1)
    # Satellite object:
    sat  = Satellite(TLE[0], TLE[1],'VPM')

    traj = []
    
    tvec = []   
    
    curtime = t1
    while curtime < t2:
        sat.compute(curtime)    
        traj.extend([sat.coords_at(curtime)])
        tvec.append(curtime)
        curtime += tstep
    traj = np.array(traj)
    
    return traj, tvec


def load_TLE_library(TLE_lib_file):
    ''' Load the JSON file of TLE entries '''

    with open(TLE_lib_file,'r') as file:
        TLE_lib = json.load(file)
        
    TLE_lib = sorted(TLE_lib, key=lambda x: x['EPOCH'])

    for T in TLE_lib:
        T['DATETIME'] = datetime.datetime.strptime(T['EPOCH'],'%Y-%m-%d %H:%M:%S')

    return TLE_lib

def get_position_from_TLE_library(timestamps, TLE_lib=None):
    '''Model the position of the satellite based on its timestamp, and a TLE.
        timestamps: a vector or list of UTC timestamps to model at
        TLE_lib: the TLE library; load it with load_TLE_library()
    '''

    # Instantiate the Satellite object
    sat = Satellite(TLE_lib[0]['TLE_LINE1'], TLE_lib[0]['TLE_LINE2'],'VPM')
    
    # Sorted vector of TLE times
    db_tvec = [x['DATETIME'] for x in TLE_lib]
    
    # Output space
    traj = []
    tvec = []
    # Get the appropriate TLE:
    for t in timestamps:
        curtime = datetime.datetime.utcfromtimestamp(t)
        
        # Grab the closest TLE (without looking into the future)
        ind = bisect.bisect_left(db_tvec, curtime)
        TLE = [TLE_lib[ind]['TLE_LINE1'],TLE_lib[ind]['TLE_LINE2']]
    
        # Update the satellite, if needed:
        sat.update_TLEs(TLE[0],TLE[1],'VPM')
    
        # Get the position
        sat.compute(curtime)    
        traj.extend([sat.coords_3d_at(curtime)])
        tvec.append(curtime)
    traj = np.array(traj)
    
    return traj, tvec



def fill_missing_GPS_entries(G_data, TLE_lib=None):
    ''' 
        Replace the lat, lon, and alt fields in a list of GPS 
        elements with synthesized values, using an appropriate TLE
        from the TLE library.
        
        For survey data ("S_data"), you can get a list of the GPS entries by:
        [x['GPS'][0] for x in S_data]
        
        For burst data, it's probably already a list of GPS entries:
        Burst_data['G']
    '''
    if not TLE_lib:
        TLE_lib = load_TLE_library('resources/VPM_TLEs.json')

    # Instantiate the Satellite object
    sat = Satellite(TLE_lib[0]['TLE_LINE1'], TLE_lib[0]['TLE_LINE2'],'VPM')
    
    # Sorted vector of TLE times
    db_tvec = [x['DATETIME'] for x in TLE_lib]
    
    # Output space
    traj = []
    tvec = []
    # Get the appropriate TLE:
    for G in G_data:
        
        # "solution_status" is defined by Novatel OEM7 manual, table 80.
        # 0 = good solution, anything else is problematic
        # time status > 20 = at least a coarse time lock
        if (G['solution_status']!=0) and (G['time_status'] > 20): 

            # Bad GPS entry! We can rebuild him... we have the technology
            t = G['timestamp']
            curtime = datetime.datetime.utcfromtimestamp(t)

            # Grab the closest TLE (without looking into the future)
            ind = bisect.bisect_left(db_tvec, curtime)
            TLE = [TLE_lib[ind]['TLE_LINE1'],TLE_lib[ind]['TLE_LINE2']]

            # Update the satellite, if needed:
            sat.update_TLEs(TLE[0],TLE[1],'VPM')

            # Get the position
            sat.compute(curtime)    
            coords = [sat.coords_3d_at(curtime)][0]

            # Write the new coordinates back to the GPS object
            # Python does everything by reference, so the S_data
            # elements are all in-place -- no returning necessary
            G['lon'] = coords[0]
            G['lat'] = coords[1]
            G['alt'] = coords[2]

