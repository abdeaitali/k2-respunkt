
import pandas as pd


def get_OTP(df_traffic):
    """
    Calculate on-time performance based on traffic data (AVL).

    Parameters:
    df_traffic (DataFrame): The traffic data containing arrival and departure information.

    Returns:
    DataFrame: Filtered data with OTP calculations.
    """

    # Keep rows where UppehållstypAnkomst is "Sista", i.e., last arrival
    df_OTP = df_traffic[df_traffic['UppehållstypAnkomst'] == 'Sista'].copy()

    # Keep uncancelled trains (i.e., rows with 'N' in 'Inställtflagga')
    df_OTP = df_OTP[df_OTP['Inställtflagga'] == 'N']

    # Ensure 'Ankomsttid' and 'Planerad ankomsttid' are datetime types
    df_OTP['Ankomsttid'] = pd.to_datetime(df_OTP['Ankomsttid'], errors='coerce')
    df_OTP['Planerad ankomsttid'] = pd.to_datetime(df_OTP['Planerad ankomsttid'], errors='coerce')
    df_OTP['Datum (PAU)'] = pd.to_datetime(df_OTP['Datum (PAU)'],errors='coerce')

    # Drop rows where conversion failed (i.e., NaT values)
    df_OTP = df_OTP.dropna(subset=['Ankomsttid', 'Planerad ankomsttid'])

    # Calculate punctuality delay at the destination station (in seconds)
    df_OTP['OTP_seconds'] = (df_OTP['Ankomsttid'] - df_OTP['Planerad ankomsttid']).dt.total_seconds()

    return df_OTP


    # Helper function to get direction
    # -1 if going north
    # +1 if going south
def get_direction(from_station, to_station, stations_south_to_north):
    if stations_south_to_north.index(from_station) < stations_south_to_north.index(to_station):
        return -1
    elif stations_south_to_north.index(from_station) > stations_south_to_north.index(to_station):
        return 1
    else:
        return 0
        

def get_PP2_A_to_B(station_A, station_B, df_traffic, df_demand, delay_threshold=5, period='morning_peak'):
    """
    Calculate PP2 on-time performance measure  based on traffic data (AVL) and passenger data.

    Parameters:
    df_traffic (DataFrame): The traffic data containing arrival and departure information.
    df_demand (DataFrame): The demand data containing passenger ridership data.

    Returns:
    DataFrame: Filtered data with PP2 calculations.
    """

    # List of stations from Nyh to Bal
    stations_order = ['Nyh', 'Gdv', 'Ngd', 'Öso', 'Ssä', 'Hfa', 'Ts', 'Kda', 'Vhe', 'Jbo', 'Hnd', 'Skg', 'Tåd', 'Fas', 'Äs', 'Åbe', 'Sst', 'Cst', 'Ke', 'Sub', 'Spå', 'Bkb', 'Jkb', 'Khä', 'Kän', 'Bro', 'Bål']
    stations_order_upper = [station.upper() for station in stations_order]

    # Morning peak time period between 6.00 and 9.00, every 15 minutes
    t_first = 6 * 4
    t_last = 9 * 4
    # by default peak morning, otherwise off-peak 9.00 to 15.00
    if(period != 'morning_peak'):
        t_first = 9 * 4
        t_last = 15 * 4
    t_period = range(t_first, t_last)
    
    delay_threshold = delay_threshold * 60  # 5 minutes (by default) delay thresholds in seconds

    # Calculate the total number of trips (T_total)
    T_total = 0
    for t in t_period:
        T_total += df_demand[t][station_A][station_B]

    # Copy of the traffic data, drop all the cancelled departures
    df_PP2 = df_traffic[df_traffic['Inställtflagga'] == 'N'].copy()

    # Departure day
    dep_day = pd.to_datetime('2015-10-14')

    df_PP2['Datum (PAU)'] = pd.to_datetime(df_PP2['Datum (PAU)'],errors='coerce')
    df_PP2['Ankomsttid'] = pd.to_datetime(df_PP2['Ankomsttid'],errors='coerce')
    df_PP2['Avgångstid'] = pd.to_datetime(df_PP2['Avgångstid'], errors='coerce')
    df_PP2['Planerad ankomsttid'] = pd.to_datetime(df_PP2['Planerad ankomsttid'],errors='coerce')
    df_PP2['Planerad avgångstid'] = pd.to_datetime(df_PP2['Planerad avgångstid'],errors='coerce')

    # Calculate the promised trips (T_promised)
    T_promised = 0
    for t in t_period:
        # Get number of passengers from A to B at time period t
        nb_pass = df_demand[t][station_A][station_B]

        # Filter all departures from A on the same departure day dep_day
        df_demand_A_B_dep_day = df_PP2[(pd.to_datetime(df_PP2['Datum (PAU)']) == dep_day) & (df_PP2['Från platssignatur'] == station_A)]

        # Drop departures in the other direction than from A to B
        dir_A_B = get_direction(station_A, station_B, stations_order)
        df_demand_A_B_dep_day = df_demand_A_B_dep_day[df_demand_A_B_dep_day.apply(lambda x: get_direction(x['Första platssignatur'], x['Sista platssignatur'].upper(), stations_order_upper) == dir_A_B, axis=1)]

        # Drop departures not serving the arrival station B
        df_demand_A_B_dep_day = df_demand_A_B_dep_day[df_demand_A_B_dep_day.apply(lambda x: get_direction(station_B.upper(), x['Sista platssignatur'].upper(), stations_order_upper)* dir_A_B>=0, axis=1)]


        # Drop all passed departures, happening earlier than t (+4 minutes for boarding/walking to the departure platform)
        df_demand_A_B_dep_day = df_demand_A_B_dep_day[(df_demand_A_B_dep_day['Planerad avgångstid'].dt.hour * 4 + (df_demand_A_B_dep_day['Planerad avgångstid'].dt.minute - 4) / 15) > t]

        # Sort the departures in terms of departure time
        df_demand_A_B_dep_day_sorted = df_demand_A_B_dep_day.sort_values(by=['Planerad avgångstid'])

        if not df_demand_A_B_dep_day_sorted.empty:
            # Get the closest next scheduled/promised departure from A
            promised_departure_row = df_demand_A_B_dep_day_sorted.iloc[0]

            # Find the corresponding promised/scheduled arrival time to B using Tåguppdrag
            promised_train_arrival = df_PP2[(df_PP2['Tåguppdrag'] == promised_departure_row['Tåguppdrag']) & (df_PP2['Till platssignatur'] == station_B)]
            promised_arrival_time = promised_train_arrival['Planerad ankomsttid'].values[0] if not promised_train_arrival.empty else None

            if promised_arrival_time is not None:
                # Find the actual departure and arrival times
                actual_departure_time = promised_departure_row['Avgångstid']
                actual_arrival_time = promised_train_arrival['Ankomsttid'].values[0] if not promised_train_arrival.empty else None

                if actual_departure_time == 'Saknas -':  # departure is cancelled
                    df_demand_A_B_dep_day_sorted = df_demand_A_B_dep_day_sorted[df_demand_A_B_dep_day_sorted['Avgångstid'] != 'Saknas -']
                    # Find the next uncancelled departure
                    if not df_demand_A_B_dep_day_sorted.empty:
                        next_departure_row = df_demand_A_B_dep_day_sorted.iloc[0]
                        actual_departure_time = next_departure_row['Avgångstid']
                        # Find the corresponding arrival
                        promised_train_arrival = df_PP2[(df_PP2['Tåguppdrag'] == next_departure_row['Tåguppdrag']) & (df_PP2['Till platssignatur'] == station_B)]
                        actual_arrival_time = promised_train_arrival['Ankomsttid'].values[0] if not promised_train_arrival.empty else None

                if actual_arrival_time is not None:
                    # Calculate the eventual delay in the arrival
                    delay = (pd.to_datetime(actual_arrival_time) - pd.to_datetime(promised_arrival_time)).total_seconds()
                    print(delay)
                    
                    # Accumulate if delay within threshold
                    if delay <= delay_threshold:
                        T_promised += nb_pass

    # Calculate the punctuality measure PP2
    PP2 = T_promised / T_total if T_total > 0 else None
    print(f'PP2 = {PP2}')


    return PP2