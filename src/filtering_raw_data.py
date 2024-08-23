import pandas as pd
import csv
import codecs # helps avoid getting "_csv.Error: line contains NUL"


# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
#   Filters obs. between Nyh-Bål from all raw traffic data
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

 
# initializing the titles and rows list and line counter
# col 1 - tåguppdrag
# col 2 - tågnr
# col 3  {"Tågordning uppdrag", Int64.Type}
# col 4 - {"Datum (PAU)", type date}
# col 5 - {"Tågslag", type text}
# col 6 - {"UppehållstypAvgång", type text}
# col 7 - {"UppehållstypAnkomst", type text}
# col 8 - {"Delsträckanummer", Int64.Type}
# col 9 - {"Första platssignatur", type text}
# col 10 - {"Första platssignatur för uppdrag", type text}
# col 11 - {"Sista platssignatur", type text}
# col 12 - {"Sista platssignatur för uppdrag", type text}

# col 13 - {"Avgångsplats", type text}
# col 14 - {"Från platssignatur", type text}

# col 15 - {"Ankomstplats", type text}
# col 16 - {"Till platssignatur", type text}
# col 17 - {"Sträcka med riktning", type text}
# col 18 - {"Inställelseorsakskod", type text}
# col 19 - {"Inställelseorsak", type text}, 
# 20 {"Ankomsttid", type text}, 
# 21 {"Avgångstid", type text}
# 22 {"Planerad ankomsttid", type datetime}, 
# 23 {"Planerad avgångstid", type datetime}, 
# 24 {"Dragfordonsid", type text}, 
# 25 {"Framförda tågkm", type text}, 
# 26 {"Rapporterad tågvikt", type text}, 
# 27 {"Rapporterad tåglängd", type text}, 
# 28 {"Antal rapporterade vagnar", Int64.Type}, 
# 29 {"Antal rapporterade hjulaxlar", Int64.Type}, 
# 30 {"Inställtflagga", type text},
# 31 {"Planeringsstatus", type text}})

#RST	Persontrafik	Tågfärd	Resandetåg
#GT	Godstrafik	Tågfärd	Godståg
#TJT	Tjänstetåg	Tågfärd	Tjänstetåg
#SPF	Godstrafik	Spärrfärd	Vagnuttagning
#VXR	Tjänstetåg	Växling	Växling

# Input and output file names
input_filename = 'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/VTI_20150101_20151231_TrafikJVG.csv'
output_filename = 'C:/Users/AbdouAA/Work Folders/Documents/GitHub/k2-respunkt/data/RST_2015_v38_42.csv'

# List of stations from Nyh to Bal
stations_order = ['Nyh', 'Gdv', 'Ngd', 'Öso', 'Ssä', 'Hfa', 'Ts', 'Kda', 'Vhe', 'Jbo', 'Hnd', 'Skg', 'Tåd', 'Fas', 'Äs', 'Åbe', 'Sst', 'Cst', 'Ke', 'Sub', 'Spå', 'Bkb', 'Jkb', 'Khä', 'Kän', 'Bro', 'Bål']

# Convert stations_order to uppercase
stations_order_upper = [station.upper() for station in stations_order]

# Define the chunk size
chunksize = 10**6

# Define the date range for weeks 38 to 42 in 2015
start_date = pd.to_datetime('2015-09-14')  # Start of week 38
end_date = pd.to_datetime('2015-10-18')    # End of week 42

# Initialize the CSV writer
with open(output_filename, 'w', newline='', encoding='utf-8') as output_file:
    writer = None

    # Process the CSV file in chunks
    for chunk in pd.read_csv(input_filename, chunksize=chunksize, delimiter=';', on_bad_lines='skip'):
        # Filter rows where column 4 ("Datum (PAU)") is within the specified date range
        chunk['Datum (PAU)'] = pd.to_datetime(chunk.iloc[:, 3], errors='coerce')
        date_filtered_chunk = chunk[(chunk['Datum (PAU)'] >= start_date) & (chunk['Datum (PAU)'] <= end_date)]
        
        # Filter rows where column 5 ("Tågslag") is "RST"
        rst_filtered_chunk = date_filtered_chunk[date_filtered_chunk.iloc[:, 4] == 'RST']

        if(len(rst_filtered_chunk)>10):
            len(rst_filtered_chunk)
            
        # Further filter rows where either column 8 ("Första platssignatur") or column 10 ("Sista platssignatur") is in stations_order_lower
        final_filtered_chunk = rst_filtered_chunk[
            rst_filtered_chunk.iloc[:, 8].isin(stations_order_upper) & rst_filtered_chunk.iloc[:, 10].isin(stations_order_upper)
        ]

        # Write the filtered chunk to the output file
        if writer is None:
            # Write the header in the first chunk
            final_filtered_chunk.to_csv(output_filename, mode='w', header=True, index=False, sep=';')
            writer = True
        else:
            # Append the subsequent chunks without the header
            final_filtered_chunk.to_csv(output_filename, mode='a', header=False, index=False, sep=';')
