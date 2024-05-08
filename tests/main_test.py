#from utils import aggregate_total_per_day
#from data_processing import read_traffic 
#from plotting import plot_VT_trip

import logging

# logging level set to INFO
logging.basicConfig(format='%(message)s',
                    level=logging.INFO)

LOG = logging.getLogger(__name__)

#######################
###     INITS
#######################

# inits for plotting and exporting
plot_ind = False
export_ind = False
head_ind = False

# path to the data files
path_name = 'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/'

#######################
##      TRAFFIC
#######################

# read traffic data
df_traffic = read_traffic()


#######################
##      DELAYS
#######################

# df_delay = get_delay_prob(df_traffic)
# df_delay_avg_std = get_delay_avg_std(df_delay)
# if export_ind:
#     df_delay.to_csv(path_name+'DF_delay.csv', index=False)
# if plot_ind:
#     plot_delay_dist_at_station(df_delay, ['Cst', 'Bkb', 'Skg'])
#     plot_delay_mean_std(df_delay_avg_std) # average delays and std per stations and direction


#######################
##      OD
#######################
    
# ### Ridership data
# # read ridership data
# df_OD = read_OD(path_name+'data_commuter.xlsx')
# if plot_ind:
#     plot_OD(df_OD)
#     plot_OD_contours(df_OD)
# if export_ind:
#     df_OD.to_csv(path_name+'DF_OD.csv', index=False)



LOG.info('--- Successfully READING, PLOTTING & EXPORTING INPUT DATA ---')
