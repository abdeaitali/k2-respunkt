from reading_data import get_traffic_data, get_demand_data
from utils import get_OTP

# read traffic data
df_traffic = get_traffic_data()

# read demand data
df_demand = get_demand_data()


OTP_seconds = get_OTP(df_traffic)
OTP_seconds[OTP_seconds['OTP_seconds'].isna()].sample(10)