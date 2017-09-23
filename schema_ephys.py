import os
import pandas as pd
import numpy as np

from current_clamp import load_current_step
from current_clamp_features import extract_istep_features
from read_metadata import *

from pymysql import IntegrityError
import datajoint as dj
schema = dj.schema('yueqi_ephys', locals())


class DjImportedFromDirectory(dj.Imported):
    # Subclass of Imported. Initialize with data directory.
    def __init__(self, directory=''):
        self.directory = directory
        super().__init__()


@schema
class EphysExperimentsForAnalysis(dj.Manual):
    definition = """
    # Organoid ephys experiments (excel files) for analysis
    experiment: varchar(128)    # excel files to use for analysis
    ---
    use: enum('Yes', 'No')      # whether to use this experiment
    """

    def insert_experiment(self, excel_file):
        '''
        Insert new organoid ephys metadata from excel to datajoint tables
        '''
        entry_list = pd.read_excel(excel_file)[['experiment', 'use']].dropna(how='any')
        entry_list = entry_list.to_dict('records')
        no_insert = True
        for entry in entry_list:
            try:
                self.insert1(row=entry)
                no_insert = False
                print("Inserted: " + str(entry))
            except IntegrityError:
                continue
        if no_insert:
            print("No new entry inserted.")
        return


@schema
class Organoids(DjImportedFromDirectory):
    definition = """
    # Organoid metadata
    -> EphysExperimentsForAnalysis
    ---
    id: varchar(128)        # organod ID (use date, but need better naming)
    strain: varchar(128)    # genetic strain
    dob = null: date        # date of birth
    date = null: date       # recording date
    age = null: smallint    # nunmber of days (date - dob)
    slicetype: varchar(128) # what kind of slice prep
    external: varchar(128)  # external solution
    internal: varchar(128)  # internal solution
    animal_comment = null: varchar(256)    # general comments
    """

    def _make_tuples(self, key):
        print('Populating for: ', key)
        animal_info, _ = read_ephys_info_from_excel_2017(
                            os.path.join(self.directory, key['experiment'] + '.xlsx'))
        key['id'] = animal_info['id']
        key['strain'] = animal_info['strain']
        if not pd.isnull(animal_info['DOB']): key['dob'] = animal_info['DOB']
        if not pd.isnull(animal_info['age']): key['age'] = animal_info['age']
        key['date'] = animal_info['date']
        key['slicetype'] = animal_info['type']
        key['external'] = animal_info['external']
        key['internal'] = animal_info['internal']
        if not pd.isnull(animal_info['comment']): key['animal_comment'] = animal_info['comment']
        self.insert1(row=key)
        return


@schema
class PatchCells(DjImportedFromDirectory):
    definition = """
    # Patch clamp metadata for each cell
    -> EphysExperimentsForAnalysis
    cell: varchar(128)      # cell id
    ---
    rp = null: float        # pipette resistance
    cm_est = null: float    # estimated Cm
    ra_est = null: float    # estimated Ra right after whole-cell mode
    rm_est = null: float    # estimated Rm
    v_rest = null: float     # resting membrane potential
    fluor = null: varchar(128)      # fluorescent label
    fill = 'No': enum('Yes', 'No')  # wether the cell is biocytin filled
    cell_external = null: varchar(128)   # external if different from organoid metadata
    cell_internal = null: varchar(128)   # internal if different from organoid metadata
    depth = null: varchar(128)      # microns beneath slice surface
    location = null: varchar(128)   # spatial location
    """

    def _make_tuples(self, key):
        print('Populating for: ', key)
        _, metadata = read_ephys_info_from_excel_2017(
                            os.path.join(self.directory, key['experiment'] + '.xlsx'))
        if 'params' in metadata.columns:
            old_file = True
            cell_info = parse_cell_info_2017_vertical(metadata)
        else:
            old_file = False
            cell_info = parse_cell_info_2017(metadata)

        for i, row in cell_info.iterrows():
            newkey = {}
            newkey['experiment'] = key['experiment']
            newkey['cell'] = row['cell']
            if not pd.isnull(row['Rp']): newkey['rp'] = row['Rp']
            if not pd.isnull(row['Cm']): newkey['cm_est'] = row['Cm']
            if not pd.isnull(row['Ra']): newkey['ra_est'] = row['Ra']
            if not pd.isnull(row['Vrest']): newkey['v_rest'] = row['Vrest']
            if not pd.isnull(row['depth']): newkey['depth'] = row['depth']

            if not old_file:
                if not pd.isnull(row['fluor']): newkey['fluor'] = row['fluor']
                if not pd.isnull(row['Rm']): newkey['rm_est'] = row['Rm']
                if not pd.isnull(row['external']): newkey['cell_external'] = row['external']
                if not pd.isnull(row['internal']): newkey['cell_internal'] = row['internal']
                if not pd.isnull(row['location']): newkey['location'] = row['location']
                if not pd.isnull(row['fill']):
                    if row['fill'].lower() in ['yes', 'no']:
                        newkey['fill'] = row['fill'].capitalize()
                    else:
                        print('"fill" must be Yes/No. ')
            self.insert1(row=newkey)
        return

@schema
class EphysRecordings(DjImportedFromDirectory):
    definition = """
    # Patch clamp metadata for each recording file
    -> EphysExperimentsForAnalysis
    cell: varchar(128)      # cell id
    recording: varchar(128) # recording file name
    ---
    clamp = null : enum('v', 'i')           # voltage or current clamp
    protocol = null : varchar(128)          # protocols such as gapfree, istep, etc
    hold = null : smallint                  # holding current or voltage
    ra_pre = null : smallint                # estimated Ra before protocol
    ra_post = null : smallint               # estimated Ra after protocol
    compensate = null : varchar(128)        # percentage of Ra compensation
    gain = null : smallint                  # amplifier gain
    filter = null : smallint                # filter in kHz
    start = null : smallint                 # current step starting current
    step = null : smallint                  # step size of current injection
    stim_strength = null : varchar(128)     # electrical/optical stimulation strength
    stim_duration = null : smallint         # duration of each stim pulse
    stim_interval = null : smallint         # interval between two consecutive pulses
    response = null : varchar(256)          # what kind of reponse was observed
    comment = null : varchar(256)           # general comments
    """

    def _make_tuples(self, key):
        print('Populating for: ', key)
        _, metadata = read_ephys_info_from_excel_2017(
                            os.path.join(self.directory, key['experiment'] + '.xlsx'))
        patch_info = parse_patch_info_2017(metadata)

        for i, row in patch_info.iterrows():
            newkey = {}
            newkey['experiment'] = key['experiment']
            newkey['cell'] = row['cell']
            newkey['recording'] = row['file']

            if not pd.isnull(row['clamp']): newkey['clamp'] = row['clamp'].lower()
            if not pd.isnull(row['protocol']): newkey['protocol'] = row['protocol']
            if not pd.isnull(row['hold']): newkey['hold'] = row['hold']
            if not pd.isnull(row['Ra-pre']):
                if type(row['Ra-pre']) is str:
                    newkey['ra_pre'] = 100
                else:
                    newkey['ra_pre'] = row['Ra-pre']
            if not pd.isnull(row['Ra-post']):
                if type(row['Ra-post']) is str:
                    newkey['ra_post'] = 100
                else:
                    newkey['ra_post'] = row['Ra-post']
            if not pd.isnull(row.get('compensate')): newkey['compensate'] = row['compensate']
            if not pd.isnull(row['gain']): newkey['gain'] = row['gain']
            if not pd.isnull(row['filter']): newkey['filter'] = row['filter']
            if not pd.isnull(row.get('start')): newkey['start'] = row['start']
            if not pd.isnull(row.get('step')): newkey['step'] = row['step']
            if not pd.isnull(row.get('stim strength')): newkey['stim_strength'] = row['stim strength']
            if not pd.isnull(row.get('stim duration')): newkey['stim_duration'] = row['stim duration']
            if not pd.isnull(row.get('stim interval')): newkey['stim_interval'] = row['stim interval']
            if not pd.isnull(row['response']): newkey['response'] = row['response']
            if not pd.isnull(row.get('comment')): newkey['comment'] = row['comment']

            self.insert1(row=newkey)
        return


@schema
class CurrentStepTimeParams(dj.Manual):
    definition = """
    # Time window parameters for current injection (account for different protocol settings)
    experiment: varchar(128)        # excel file names (experiment name)
    ---
    istep_start: float      # current injection starting time (s)
    istep_end: float        # current injection ending time (s)
    istep_duration: float   # current injection duration (s)
    """

    def insert_params(self, excel_file):
        '''
        Insert paramters for current injection
        '''
        entry_list = pd.read_excel(excel_file)[['experiment', 'istep_start', 'istep_duration']]
        entry_list = entry_list.dropna(how='any').to_dict('records')
        no_insert = True
        for entry in entry_list:
            entry['istep_end'] = entry['istep_start'] + entry['istep_duration']
            try:
                self.insert1(row=entry)
                no_insert = False
                print("Inserted: " + str(entry))
            except IntegrityError:
                continue
        if no_insert:
            print("No new entry inserted.")
        return

@schema
class APandIntrinsicProperties(DjImportedFromDirectory):
    definition = """
    # Action potential and intrinsic properties from current injections
    -> EphysExperimentsForAnalysis
    cell: varchar(128)      # cell id
    recording: varchar(128) # recording file name
    ---
    has_ap : enum('Yes', 'No')
    v_baseline = null : float
    bias_current = null : float
    tau = null : float
    capacitance = null : float
    input_resistance = null : float
    f_i_curve_slope = null : float

    ap_threshold = null : float
    ap_width = null : float
    ap_height = null : float
    ap_peak = null : float
    ap_trough = null : float
    ap_trough_to_threshold = null : float
    ap_upstroke = null : float
    ap_downstroke = null : float
    ap_updownstroke_ratio = null : float

    rheobase_index = null : float
    rheobase_stim_amp = null : float

    adaptation = null : float
    avg_isi = null : float
    latency = null : float

    hero_sweep_index = null : float
    hero_sweep_stim_amp = null : float

    sag = null : float
    vm_for_sag = null : float

    """
    def _make_tuples(self, key):

        istep_start, istep_end = \
                (CurrentStepTimeParams() & key).fetch1('istep_start', 'istep_end')

        this_organoid = (EphysExperimentsForAnalysis() & key)
        all_istep_recordings = (EphysRecordings()  & "protocol = 'istep'")
        cells, istep_recordings = (all_istep_recordings * this_organoid).fetch('cell','recording')

        for cell, rec in zip(cells, istep_recordings):
            print('Populating for: ' + key['experiment'] + ' ' + rec)
            abf_file = os.path.join(self.directory, key['experiment'], rec + '.abf')
            data = load_current_step(abf_file)
            cell_features, summary_features = \
                        extract_istep_features(data, start=istep_start, end=istep_end, subthresh_min_amp=-50)
            newkey = summary_features.copy()
            newkey['has_ap'] = 'Yes' if summary_features['has_ap'] else 'No'
            newkey['experiment'] = key['experiment']
            newkey['cell'] = cell
            newkey['recording'] = rec
            newkey.pop('file_id', None)
            self.insert1(row=newkey)
        return
