"""This file gets dataframes from mongoDB and saves them in the corresponding locations. The data that is pulled from mongoDB is—at least in the hardcoded iterations—the data that was used in the NeurIPS 2021 submission. Make sure to run `ssh -fNL 27017:127.0.0.1:27017 USERNAME@cogtoolslab.org` to set up the mongoDB connection as well as provide auth.txt in the same folder as this file."""

import os
import sys
import urllib, io
os.getcwd()
sys.path.append("..")
sys.path.append("../utils")
sys.path.append("../analysis/utils")

import numpy as np
import scipy.stats as stats
import pandas as pd

import pymongo as pm
from collections import Counter
import json
import re
import ast

from PIL import Image, ImageOps, ImageDraw, ImageFont 

from io import BytesIO
import base64

from tqdm import tqdm

import  matplotlib
from matplotlib import pylab, mlab, pyplot
import matplotlib.pyplot as plt
from IPython.core.pylabtools import figsize, getfigs
plt = pyplot
import matplotlib as mpl
mpl.rcParams['pdf.fonttype'] = 42
plt.style.use('seaborn-white')

import seaborn as sns
sns.set_context('talk')
sns.set_style('darkgrid')
from IPython.display import clear_output

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="numpy.dtype size changed")
warnings.filterwarnings("ignore", message="numpy.ufunc size changed")

#helper function for pd.agg
def item(x):
    """Returns representative single item"""
    return x.tail(1).item()

# set up directories
## directory & file hierarchy
proj_dir = os.path.abspath('../')
analysis_dir =  os.path.abspath('.')
results_dir = os.path.join(proj_dir,'results')
csv_dir = os.path.join(results_dir,'csv/humans')

## add helpers to python path
if os.path.join(proj_dir,'stimuli') not in sys.path:
    sys.path.append(os.path.join(proj_dir,'stimuli'))
    
if not os.path.exists(results_dir):
    os.makedirs(results_dir)
    
if not os.path.exists(csv_dir):
    os.makedirs(csv_dir)       
    
## add helpers to python path
if os.path.join(proj_dir,'utils') not in sys.path:
    sys.path.append(os.path.join(proj_dir,'utils'))   

def make_dir_if_not_exists(dir_name):   
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    return dir_name

## create directories that don't already exist        
result = [make_dir_if_not_exists(x) for x in [results_dir,csv_dir]]

# set vars 
try:
    auth = pd.read_csv(os.path.join(proj_dir,'auth.txt'), header = None) # this auth.txt file contains the password for the sketchloop user. Place in repo folder
except: 
    print('ERROR: Before you can generate dataframes, please make sure you have the auth.txt file with mongodb credentials.')
    sys.exit()
pswd = auth.values[0][0]
user = 'sketchloop'
host = 'cogtoolslab.org'

# have to fix this to be able to analyze from local
import pymongo as pm
conn = pm.MongoClient('mongodb://sketchloop:' + pswd + '@127.0.0.1')

neurips2021_iterations = [
    {'study' : "dominoes_pilot",
    'bucket_name' : 'human-physics-benchmarking-dominoes-pilot',
    'stim_version' : 'production_1',
    'iterationName' : 'production_1_testing'},
    {'study' : "collision_pilot",
    'bucket_name' : 'human-physics-benchmarking-collision-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
    {'study' : "towers_pilot",
    'bucket_name' : 'human-physics-benchmarking-towers-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
    {'study' : "linking_pilot",
    'bucket_name' : 'human-physics-benchmarking-linking-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
    {'study' : "containment_pilot",
    'bucket_name' : 'human-physics-benchmarking-containment-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
    {'study' : "rollingsliding_pilot",
    'bucket_name' : 'human-physics-benchmarking-rollingsliding-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
    {'study' : "drop_pilot",
    'bucket_name' : 'human-physics-benchmarking-drop-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
    {'study' : "clothiness_pilot",
    'bucket_name' : 'human-physics-benchmarking-clothiness-pilot',
    'stim_version' : 'production_2',
    'iterationName' : 'production_2_testing'},
]

def get_dfs_from_mongo(study,bucket_name,stim_version,iterationName):
    """Get's and saves the given iteration from the mongoDB. Writes out two dataframes."""
    # connect to database
    db = conn['human_physics_benchmarking']
    coll = db[study]
    stim_db = conn['stimuli']
    stim_coll = stim_db[bucket_name+'_'+stim_version]

    # get dataframe of served stims
    stim_df = pd.DataFrame(stim_coll.find({}))
    stim_df.set_index('_id')
    df = coll.find({
            'iterationName':iterationName
    #             'prolificID': {'$exists' : True},
    #             'studyID': {'$exists' : True},
    #             'sessionID': {'$exists' : True},
    })
    df = pd.DataFrame(df)
    
    assert len(df)>0, "df from mongo empty"

    #Which gameids have completed all trials that were served to them? 
    #Note that this will also exclude complete trials whose games aren't in the stim database anymore (ie if it has been dropped)
    complete_gameids = []
    for gameid in tqdm(df['gameID'].unique()):
        #get the corresponding games
        served_stim_ID = None
        for stims_ID in stim_df.index:
            try:
                if gameid in stim_df.iloc[stims_ID]['games']:
                    #great, we found our corresponding stim_ID
                    served_stim_ID = stims_ID
            except TypeError as e:
    #             print("No games listed for",stims_ID)
                    pass
        if served_stim_ID == None:
            #we haven't found the stim_ID
            print("No recorded entry for game_ID in stimulus database:",gameid)
            continue
        served_stims = stim_df.at[served_stim_ID,'stims']
        #let's check if we can find an entry for each stim
        found_empty = False
        for stim_ID in [s['stim_ID'] for s in served_stims.values()]:
            #check if we have an entry for that stimulus
            if len(df.query("gameID == '"+gameid+"' & stim_ID == '"+stim_ID+"'")) == 0:
                found_empty = True
                break
        if not found_empty: complete_gameids.append(gameid)
    
    #mark unfinished entries
    df['complete_experiment'] = df['gameID'].isin(complete_gameids) 
    # # we only consider the first 100 gameIDs
    # complete_gameids = complete_gameids[:100]       
    #exclude unfinished games ⚠️
    df = df[df['gameID'].isin(complete_gameids)]
    #Generate some useful views
    df_trial_entries = df[(df['condition'] == 'prediction') & (df['trial_type'] == 'video-overlay-button-response')] #only experimental trials
    df_trial_entries['study'] = [study]*len(df_trial_entries)
    # save out df_trials_entries
    df_trial_entries.to_csv(os.path.join(csv_dir,"human_responses-{}-{}.csv".format(study,iterationName)))

    #generate per stim aggregated df
    df_trial_entries['c'] = 1 #add dummy variable for count in agg
    per_stim_agg = df_trial_entries.groupby('stim_ID').agg({
        'correct' : lambda cs: np.mean([1 if c == True else 0 for c in cs]),
        'c' : 'count',
    })
    #save
    per_stim_agg.to_csv(os.path.join(csv_dir,"human_accuracy-{}-{}.csv".format(study,iterationName)))
    return

if __name__ == "__main__":
    print("Fetching neurIPS 2021 results")
    for i,it_fields in enumerate(neurips2021_iterations):
        print("Fetching",i+1,"from",len(neurips2021_iterations),"—",it_fields['study'])
        get_dfs_from_mongo(**it_fields)
    print("Done.")