import streamlit as st
import pandas as pd
import numpy as np
import io

# Title for Streamlit app
st.title("Dopamine Release and Running Analysis")

# File uploaders for running data and dopamine data
running_file = st.file_uploader("Upload Running Data File", type=["xlsx"])
dopamine_file = st.file_uploader("Upload Dopamine Data File", type=["xlsx"])

# Parameter inputs
running_bout_length = st.slider("Running Bout Length (in seconds)", min_value=1, max_value=10, value=2)
sedentary_bout_length = st.slider("Sedentary Bout Length (in seconds)", min_value=5, max_value=30, value=20)
pre_running_seconds = st.slider("Seconds Before Running Bout to Analyze", min_value=0, max_value=10, value=5)
post_running_seconds = st.slider("Seconds After Running Bout to Analyze", min_value=0, max_value=10, value=5)
pre_offset_seconds = st.slider("Seconds Before Running Bout Ends to Analyze", min_value=0, max_value=10, value=5)
running_measure = st.selectbox("Select Running Measure", ['Interval Count', 'Average m/min', 'Distance'])

# Proceed if both files are uploaded
if running_file is not None and dopamine_file is not None:
    # Load Running Data
    running_data_raw = pd.read_excel(running_file, header=None)

    # Initialize lists to store extracted data
    times, interval_counts, average_mins, distances, total_counts = [], [], [], [], []

    # Extract relevant rows from running data
    for i in range(len(running_data_raw)):
        first_cell = str(running_data_raw.iloc[i, 0]).strip()
        try:
            time_value = pd.to_datetime(first_cell, format="%H:%M:%S", errors='coerce')
            if not pd.isna(time_value):
                times.append(first_cell)
                try:
                    interval_counts.append(running_data_raw.iloc[i + 1, 1])
                    average_mins.append(running_data_raw.iloc[i + 2, 1])
                    distances.append(running_data_raw.iloc[i + 3, 1])
                    total_counts.append(running_data_raw.iloc[i + 4, 1])
                except IndexError:
                    break
        except ValueError:
            continue

    # Create DataFrame for running data
    running_data = pd.DataFrame({
        'Time': times,
        'Interval Count': interval_counts,
        'Average m/min': average_mins,
        'Distance': distances,
        'Total Counts': total_counts
    })

    # Assign integer-based time for merging
    running_data['Time (seconds)'] = range(len(running_data))

    # Load and process dopamine data
    dopamine_data = pd.read_excel(dopamine_file)
    dopamine_data.columns = dopamine_data.columns.str.strip()

    dopamine_data['file'] = os.path.basename(dopamine_file.name)

    # Calculate average dopamine concentration per second
    dopamine_per_second = {}
    for second in range(int(dopamine_data['Time (seconds)'].max()) + 1):
        dopamine_in_current_second = dopamine_data[
            (dopamine_data['Time (seconds)'] >= second) &
            (dopamine_data['Time (seconds)'] < second + 1)
        ]
        if not dopamine_in_current_second.empty:
            avg_concentration = dopamine_in_current_second['Concentration'].mean()
            file_name = dopamine_in_current_second['file'].iloc[0]
            dopamine_per_second[second] = (avg_concentration, file_name)
        else:
            dopamine_per_second[second] = (np.nan, None)

    # Convert dictionary to DataFrame
    dopamine_df = pd.DataFrame.from_dict(dopamine_per_second, orient='index', columns=['Avg Dopamine Concentration', 'File Name'])
    dopamine_df.index.name = 'Time (seconds)'
    dopamine_df.reset_index(inplace=True)

    # Combine running and dopamine data
    combined_data = pd.merge(running_data, dopamine_df, how='left', on='Time (seconds)')
    
    # Assign File Numbers based on row index (every 60 rows = new file number)
    combined_data['File Number'] = ((combined_data.index) // 60) + 1


    # Identify sedentary bouts
    sedentary_bouts = []
    for i in range(len(running_data)):
        if running_data['Average m/min'][i] == 0:
            bout_start = max(0, i - sedentary_bout_length)
            bout_end = min(len(running_data) - 1, i + sedentary_bout_length)
            if all(running_data['Average m/min'][bout_start:bout_end + 1] == 0):
                sedentary_bouts.extend(range(bout_start, bout_end + 1))

    sedentary_bouts = list(set(sedentary_bouts))

    # Add sedentary bouts to combined data
    combined_data['Sedentary Bout'] = combined_data['Time (seconds)'].apply(lambda x: 'Yes' if x in sedentary_bouts else 'No')

    # Identify running bouts
    running_bouts = []
    current_running_bout = []

    for i in range(len(running_data)):
        if running_data['Average m/min'][i] > 0:
            current_running_bout.append(running_data['Time (seconds)'][i])
        else:
            if len(current_running_bout) >= running_bout_length:
                running_bouts.append(current_running_bout)
            current_running_bout = []

    if len(current_running_bout) >= running_bout_length:
        running_bouts.append(current_running_bout)

    # Analyze dopamine release before, during, and after running bouts
    dopamine_before, dopamine_after, dopamine_offset, dopamine_during = [], [], [], []

    for bout in running_bouts:
        bout_start, bout_end = bout[0], bout[-1]

        # Dopamine before the bout
        before_data = combined_data[
            (combined_data['Time (seconds)'] >= bout_start - pre_running_seconds) &
            (combined_data['Time (seconds)'] < bout_start) &
            (combined_data['Avg Dopamine Concentration'].notna()) &
            (combined_data['Average m/min'] == 0)
        ]
        dopamine_before.extend(before_data.values.tolist())

        # Dopamine after the bout
        after_data = combined_data[
            (combined_data['Time (seconds)'] > bout_end) &
            (combined_data['Time (seconds)'] <= bout_end + post_running_seconds) &
            (combined_data['Avg Dopamine Concentration'].notna()) &
            (combined_data['Average m/min'] == 0)
        ]
        dopamine_after.extend(after_data.values.tolist())

        # Dopamine offset (during running)
        offset_data = combined_data[
            (combined_data['Time (seconds)'] >= bout_end - pre_offset_seconds) &
            (combined_data['Time (seconds)'] < bout_end) &
            (combined_data['Avg Dopamine Concentration'].notna()) &
            (combined_data['Average m/min'] > 0)
        ]
        dopamine_offset.extend(offset_data.values.tolist())
        
        # Dopamine DURING the bout (every second during running)
        during_data = combined_data[
            (combined_data['Time (seconds)'] >= bout_start) &  # From start of bout
            (combined_data['Time (seconds)'] <= bout_end) &  # Until end of bout
            (combined_data['Avg Dopamine Concentration'].notna()) &  # Ensure dopamine exists
            (combined_data['Average m/min'] > 0)  # Ensure the rat is running
        ]
        dopamine_during.extend(during_data.values.tolist())
    
    # Create DataFrames
    dopamine_analysis_before_df = pd.DataFrame(dopamine_before, columns=combined_data.columns)
    dopamine_analysis_after_df = pd.DataFrame(dopamine_after, columns=combined_data.columns)
    dopamine_analysis_offset_df = pd.DataFrame(dopamine_offset, columns=combined_data.columns)
    dopamine_analysis_during_df = pd.DataFrame(dopamine_during, columns=combined_data.columns)
    
    # Sedentary bouts data
    sedentary_bouts_expanded = []
    for time in sedentary_bouts:
        row = combined_data[combined_data['Time (seconds)'] == time].iloc[0]
        if pd.notna(row['Avg Dopamine Concentration']):
            sedentary_bouts_expanded.append(row.values.tolist())

    sedentary_bouts_df = pd.DataFrame(sedentary_bouts_expanded, columns=combined_data.columns)

    # Save to Excel
    if st.button("Save Combined Data to Excel"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            combined_data.to_excel(writer, sheet_name='Combined Data', index=False)
            dopamine_analysis_during_df.to_excel(writer, sheet_name='Dopamine During', index=False)
            dopamine_analysis_before_df.to_excel(writer, sheet_name='Dopamine Before', index=False)
            dopamine_analysis_offset_df.to_excel(writer, sheet_name='Dopamine Offset', index=False)
            dopamine_analysis_after_df.to_excel(writer, sheet_name='Dopamine After', index=False)
            sedentary_bouts_df.to_excel(writer, sheet_name='Sedentary Bouts', index=False)
           
            
        output.seek(0)
        st.download_button(
            label="Save As...",
            data=output,
            file_name="combined_running_dopamine_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
