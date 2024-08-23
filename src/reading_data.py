import pandas as pd


######################
##  Reading traffic data
#######################
def get_traffic_data():
    input_file = 'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/RST_2015_v38_42.csv'
    traffic_data = pd.read_csv(input_file, delimiter=';')
    return traffic_data


######################
##  Reading demand data
#######################
def get_demand_data():
    # load dataset
    input_file = 'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/OD_data_dynamic.xlsx'
    df_static = pd.read_excel(input_file, sheet_name='Static', index_col=0, header=0)

    # Extract headers and index from the static data
    headers = df_static.columns
    index = df_static.index

    # Number of time periods (every 15 minutes during a full day)
    nb_time_periods = int(24 * 60 / 15)  # 96 periods

    # Initialize a dictionary to store DataFrames for each time period
    df_sheets = {}

    # Read specific sheets by index
    for t in range(nb_time_periods):
        sheet_name = f"Sheet{t+1}"  # Assuming sheet names are "Sheet1", "Sheet2", ..., "Sheet96"
        df_temp = pd.read_excel(input_file, sheet_name=sheet_name, header=None)  # Read without headers
        
        # Assign the headers and index from the static data
        df_temp.columns = headers
        df_temp.index = index
        
        # Store the DataFrame in the dictionary
        df_sheets[t] = df_temp
    return df_sheets