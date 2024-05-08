import pandas as pd

def read_traffic(remove_weekends=True):
    input_file = 'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/filter_traffic_data_pendeltag_Bal_Nyh_2015.csv'
    df = pd.read_csv(input_file, delimiter=',')

    # drop observation of departures which are not in the studied stations
    # Your list of valid values
    valid_values = ['Bål', 'Bro', 'Kän', 'Khä', 'Jkb', 'Bkb', 'Spå', 'Sub', 'Ke', 'Cst', 'Sst', 'Åbe', 'Äs', 'Fas', 'Tåd',
                    'Skg', 'Hnd', 'Jbo', 'Vhe', 'Kda', 'Ts', 'Hfa', 'Ssä', 'Öso', 'Ngd', 'Gdv', 'Nyh']

    # Filter rows based on the 'Från platssignatur' column
    df_filtered = df[df['Från platssignatur'].isin(valid_values)]

    # Create a dictionary mapping each station to its index in the north-to-south order
    station_index_mapping = {station: index for index, station in enumerate(valid_values)}

    # Create 'Direction' column based on the mapping for both 'Från platssignatur' and 'Till platssignatur'
    df_filtered['Direction_From'] = df_filtered['Första platssignatur'].str.capitalize().map(station_index_mapping)
    df_filtered['Direction_To'] = df_filtered['Sista platssignatur'].str.capitalize().map(station_index_mapping)

    # Assign direction based on the comparison of indices
    df_filtered['Direction'] = (df_filtered['Direction_To'] < df_filtered['Direction_From']).astype(int)

    if(remove_weekends): # keep only working days (i.e., remove weekend data)
        # Assuming df_traffic is your DataFrame
        df_filtered['Avgångstid'] = pd.to_datetime(df_filtered['Avgångstid'])

        # Extract the day of the week information
        df_filtered['DayOfWeek'] = df_filtered['Avgångstid'].dt.dayofweek

        # Filter out weekends (Saturday and Sunday)
        df_filtered = df_filtered[(df_filtered['DayOfWeek'] >= 0) & (df_filtered['DayOfWeek'] < 5)]
        
    return df_filtered
