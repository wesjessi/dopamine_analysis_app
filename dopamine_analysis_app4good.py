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
running_measure = st.selectbox("Select Running Measure", ['Interval Count', 'Average m/min', 'Distance'])

# Proceed if both files are uploaded
if running_file is not None and dopamine_file is not None:
    # Load Running Data
    running_data_raw = pd.read_excel(running_file, header=None)

    # Initialize lists to store the extracted data
    times = []
    interval_counts = []
    average_mins = []
    distances = []
    total_counts = []

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

    # Create a new DataFrame for running data
    running_data = pd.DataFrame({
        'Time': times,
        'Interval Count': interval_counts,
        'Average m/min': average_mins,
        'Distance': distances,
        'Total Counts': total_counts
    })

    # Load and process dopamine data
    dopamine_data = pd.read_excel(dopamine_file)
    dopamine_data.columns = dopamine_data.columns.str.strip()

    # Calculate average dopamine concentration per second
    dopamine_per_second = {}
    for second in range(int(dopamine_data['Time (seconds)'].max()) + 1):
        start_time = second
        end_time = second + 0.9
        dopamine_in_current_second = dopamine_data[(dopamine_data['Time (seconds)'] >= start_time) & (dopamine_data['Time (seconds)'] <= end_time)]
        if not dopamine_in_current_second.empty:
            avg_concentration = dopamine_in_current_second['Concentration'].mean()
            dopamine_per_second[second] = avg_concentration
        else:
            dopamine_per_second[second] = np.nan

    dopamine_df = pd.DataFrame(list(dopamine_per_second.items()), columns=['Time (seconds)', 'Avg Dopamine Concentration'])

    # Combine running data and dopamine data
    running_data['Time (seconds)'] = range(len(running_data))
    combined_data = pd.merge(running_data, dopamine_df, how='left', on='Time (seconds)')

    # Identify sedentary bouts: Every second within 20 seconds before and after should be sedentary
    sedentary_bouts = []
    for i in range(len(running_data)):
        if running_data['Average m/min'][i] == 0:
            bout_start = max(0, i - sedentary_bout_length)
            bout_end = min(len(running_data) - 1, i + sedentary_bout_length)
            if all(running_data['Average m/min'][bout_start:bout_end + 1] == 0):
                sedentary_bouts.extend(range(bout_start, bout_end + 1))

    # Remove duplicate entries from sedentary_bouts
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

    # Analyze dopamine release before and after running bouts
    dopamine_before = []
    dopamine_after = []

    for bout in running_bouts:
        bout_start = bout[0]
        bout_end = bout[-1]

        # Dopamine before the bout (only if not running)
        before_data = combined_data[(combined_data['Time (seconds)'] >= bout_start - pre_running_seconds) & 
                                    (combined_data['Time (seconds)'] < bout_start)]
        before_data = before_data[(before_data['Avg Dopamine Concentration'].notna()) & (before_data['Average m/min'] == 0)]
        # Debugging: Check filtered before_data
        
        for _, row in before_data.iterrows():
            dopamine_before.append([row['Time (seconds)'], row['Avg Dopamine Concentration']])

        # Dopamine after the bout (only if not running)
        after_data = combined_data[(combined_data['Time (seconds)'] > bout_end) & 
                                   (combined_data['Time (seconds)'] <= bout_end + post_running_seconds)]
        after_data = after_data[(after_data['Avg Dopamine Concentration'].notna()) & (after_data['Average m/min'] == 0)]
        # Debugging: Check filtered after_data

        for _, row in after_data.iterrows():
            dopamine_after.append([row['Time (seconds)'], row['Avg Dopamine Concentration']])

    # Create DataFrames for each analysis
    running_bouts_expanded = []
    for bout in running_bouts:
        for time in bout:
            row = combined_data[combined_data['Time (seconds)'] == time].iloc[0]
            if pd.notna(row['Avg Dopamine Concentration']):
                running_bouts_expanded.append([row['Time'], row['Interval Count'], row['Average m/min'], row['Avg Dopamine Concentration']])

    running_bouts_df = pd.DataFrame(running_bouts_expanded, columns=['Time', 'Interval Count', 'Average m/min', 'Dopamine'])

    dopamine_before_expanded = []
    for item in dopamine_before:
        time = item[0]
        concentration = item[1]
        row = combined_data[combined_data['Time (seconds)'] == time].iloc[0]
        dopamine_before_expanded.append([row['Time'], row['Interval Count'], row['Average m/min'], concentration])

    dopamine_after_expanded = []
    for item in dopamine_after:
        time = item[0]
        concentration = item[1]
        row = combined_data[combined_data['Time (seconds)'] == time].iloc[0]
        dopamine_after_expanded.append([row['Time'], row['Interval Count'], row['Average m/min'], concentration])

    dopamine_analysis_before_df = pd.DataFrame(dopamine_before_expanded, columns=['Time', 'Interval Count', 'Average m/min', 'Dopamine Before'])
    dopamine_analysis_after_df = pd.DataFrame(dopamine_after_expanded, columns=['Time', 'Interval Count', 'Average m/min', 'Dopamine After'])

    sedentary_bouts_expanded = []
    for time in sedentary_bouts:
        row = combined_data[combined_data['Time (seconds)'] == time].iloc[0]
        if pd.notna(row['Avg Dopamine Concentration']):
            sedentary_bouts_expanded.append([row['Time'], row['Interval Count'], row['Average m/min'], row['Avg Dopamine Concentration']])

    sedentary_bouts_df = pd.DataFrame(sedentary_bouts_expanded, columns=['Time', 'Interval Count', 'Average m/min', 'Dopamine'])

    # Option to save to Excel
    if st.button("Save Combined Data to Excel"):
        # Create a BytesIO buffer to save the Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            combined_data.to_excel(writer, sheet_name='Combined Data', index=False)
            running_bouts_df.to_excel(writer, sheet_name='Running Bouts', index=False)
            dopamine_analysis_before_df.to_excel(writer, sheet_name='Dopamine Before', index=False)
            dopamine_analysis_after_df.to_excel(writer, sheet_name='Dopamine After', index=False)
            sedentary_bouts_df.to_excel(writer, sheet_name='Sedentary Bouts', index=False)

        # Save the Excel file in the BytesIO buffer
        output.seek(0)

        # Offer the file for download using download_button
        st.download_button(
            label="Save As...",
            data=output,
            file_name="combined_running_dopamine_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
