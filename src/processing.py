import pandas as pd


def process_traffic_data(df):
    # remove useless columns
    columns_to_drop = [4, 23, 25, 26, 27, 28]
    df_filtered = df.drop(columns=df.columns[columns_to_drop])

    # Convert relevant date and time columns to datetime format
    df_filtered['Datum (PAU)'] = pd.to_datetime(df_filtered['Datum (PAU)'],errors='coerce')
    df_filtered['Ankomsttid'] = pd.to_datetime(df_filtered['Ankomsttid'],errors='coerce')
    df_filtered['Avgångstid'] = pd.to_datetime(df_filtered['Avgångstid'], errors='coerce')
    df_filtered['Planerad ankomsttid'] = pd.to_datetime(df_filtered['Planerad ankomsttid'],errors='coerce')
    df_filtered['Planerad avgångstid'] = pd.to_datetime(df_filtered['Planerad avgångstid'],errors='coerce')
    
    # keep only weekdays
    df_filtered = df_filtered[df_filtered['Datum (PAU)'].dt.weekday < 5]