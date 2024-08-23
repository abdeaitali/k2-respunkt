import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline


def plot_OTP(df_OTP_sec, periodicity='all'):
    """
    Plot on-time performance based on delay thresholds.

    Parameters:
    df_OTP_sec (DataFrame): DataFrame containing OTP calculations in seconds.
    periodicity (str): 'all' for overall, 'day' for daily variations, 'hour' for hourly variations.

    Returns:
    None
    """

    # Define a range of delay thresholds up to 30 minutes
    delay_thresholds = np.linspace(0, 30, 100)
    OTP_within_threshold = []

    # Calculate the percentage of trains within each delay threshold
    total_valid_arrivals = len(df_OTP_sec)

    for threshold in delay_thresholds:
        num_within_threshold = np.sum(df_OTP_sec['OTP_seconds'] / 60 <= threshold)
        OTP_within_threshold.append((num_within_threshold / total_valid_arrivals) * 100)


    if periodicity == 'all':
        # Plotting the results for overall OTP
        plt.figure(figsize=(12, 8))
        plt.plot(delay_thresholds, OTP_within_threshold, linestyle='-', label='OTP (excl. cancellations)')
        plt.legend()
        plt.xlabel('Delay Threshold (minutes)')
        plt.ylabel('Percentage of Trains Arriving Within Threshold (%)')
        plt.title('Percentage of Trains Arriving Within Delay Thresholds')
        plt.xticks(range(0, 31, 5))
        plt.grid(True)
        plt.show()

    elif periodicity == 'day':
        # Calculate average OTP for each weekday (Monday to Sunday)
        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        df_OTP_sec['Weekday'] = df_OTP_sec['Datum (PAU)'].dt.day_name()
        df_weekday_OTP = pd.DataFrame(columns=weekdays, index=np.arange(len(delay_thresholds)))

        for i, threshold in enumerate(delay_thresholds):
            for weekday in weekdays:
                # Filter data for the current weekday and delay threshold
                weekday_data = df_OTP_sec[(df_OTP_sec['Weekday'] == weekday) & (df_OTP_sec['OTP_seconds'] / 60 <= threshold)]
                df_weekday_OTP.loc[i, weekday] = len(weekday_data) / len(df_OTP_sec[df_OTP_sec['Weekday'] == weekday]) * 100

        # Plotting daily variation OTP
        plt.figure(figsize=(12, 8))
        for weekday in weekdays:
            plt.plot(delay_thresholds, df_weekday_OTP.loc[:, weekday], label=weekday)

        plt.plot(delay_thresholds, OTP_within_threshold, linestyle='-', label='All')

        plt.legend(title='Time periods')
        plt.xlabel('Delay Threshold (minutes)')
        plt.ylabel('Percentage of Trains Arriving Within Threshold (%)')
        plt.title('Average Daily Variation of On-Time Performance')
        plt.xticks(range(0, 31, 5))
        plt.grid(True)
        plt.show()

    elif periodicity == 'hour':

# Categorize hours into specific periods
        df_OTP_sec['Hour'] = df_OTP_sec['Ankomsttid'].dt.hour
        hour_bins = [6, 9, 15, 18]
        hour_labels = ['Morning Peak', 'Midday Off-Peak', 'Afternoon Peak']

        # Use pd.cut to categorize each hour into the appropriate period
        df_OTP_sec['Hour Period'] = pd.cut(df_OTP_sec['Hour'], bins=hour_bins, labels=hour_labels, ordered=False)

        # Calculate average OTP for each hour period
        df_hourly_OTP = pd.DataFrame(columns=['OTP Percentage'], index=hour_labels)

        for period in hour_labels:
            # Filter data for the current hour period and calculate OTP percentage
            period_data = df_OTP_sec[df_OTP_sec['Hour Period'] == period]
            OTP_percentage = []
            for threshold in delay_thresholds:
                num_within_threshold = np.sum(period_data['OTP_seconds'] / 60 <= threshold)
                OTP_percentage.append((num_within_threshold / len(period_data)) * 100)
            df_hourly_OTP.loc[period, 'OTP Percentage'] = OTP_percentage

        # Plotting hourly variation OTP
        plt.figure(figsize=(12, 8))
        for period in hour_labels:
            plt.plot(delay_thresholds, df_hourly_OTP.loc[period, 'OTP Percentage'], label=period)

        plt.plot(delay_thresholds, OTP_within_threshold, linestyle='-', label='All')

        plt.legend(title='Time periods')
        plt.xlabel('Delay Threshold (minutes)')
        plt.ylabel('Percentage of Trains Arriving Within Threshold (%)')
        plt.title('Average Hourly Variation of On-Time Performance')
        plt.xticks(range(0, 31, 5))
        plt.grid(True)
        plt.show()

    else:
        print("Invalid periodicity option. Choose from 'all', 'day', or 'hour'.")




def plot_PP2(df_pp, also=''):
    """
    Plot Combined Performance Measure (CPM), i.e., OTP including cancellations.

    Parameters:
    df_traffic (DataFrame): DataFrame containing traffic data.
    df_demand (DataFrame): DataFrame containing passenger demand data.
    also (str): '' plot CPM only with OTP, 'PP2' also with PP2.

    Returns:
    None
    """

