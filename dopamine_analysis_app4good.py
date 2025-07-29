import streamlit as st
import pandas as pd
import numpy as np
import io
import os

st.title("Dopamine Release and Running Analysis")

# ─── Step 1: Upload & Assess Running Data ──────────────────────────────────────
running_file = st.file_uploader("1) Upload Running Data File", type=["xlsx"], key="run_file")
if running_file:
    if st.button("Assess Running Data"):
        # Parse the raw running Excel as before
        running_data_raw = pd.read_excel(running_file, header=None)
        times, interval_counts, average_mins, distances, total_counts = [], [], [], [], []
        for i in range(len(running_data_raw)):
            cell = str(running_data_raw.iloc[i, 0]).strip()
            t = pd.to_datetime(cell, format="%H:%M:%S", errors="coerce")
            if not pd.isna(t):
                times.append(cell)
                try:
                    interval_counts.append(running_data_raw.iloc[i+1, 1])
                    average_mins.append(running_data_raw.iloc[i+2, 1])
                    distances.append(running_data_raw.iloc[i+3, 1])
                    total_counts.append(running_data_raw.iloc[i+4, 1])
                except IndexError:
                    break
        running_data = pd.DataFrame({
            'Time': times,
            'Interval Count': interval_counts,
            'Average m/min': average_mins,
            'Distance': distances,
            'Total Counts': total_counts
        })
        running_data['Time (seconds)'] = range(len(running_data))
        
        # Basic running-bout detection at default length=2s
        bouts = []
        current = []
        for idx, spd in enumerate(running_data['Average m/min']):
            if spd > 0:
                current.append(idx)
            else:
                if len(current) >= 1:
                    bouts.append(current)
                current = []
        if len(current) >= 2:
            bouts.append(current)
        
        # Compute summary metrics
        num_bouts  = len(bouts)
        lengths    = [len(b) for b in bouts]
        avg_length = np.mean(lengths) if lengths else 0
        avg_speed  = np.mean([
            running_data.loc[b, 'Average m/min'].mean() 
            for b in bouts
        ]) if bouts else 0
        max_speed  = running_data['Average m/min'].max()
        bins = {
            '1 sec':     sum(1 for L in lengths if   L == 1),
            '2–5 sec':   sum(1 for L in lengths if 2 <= L <= 5),
            '6–10 sec':  sum(1 for L in lengths if 6 <= L <= 10),
            '>10 sec':   sum(1 for L in lengths if   L > 10),
        }
        
        # Display them
        st.subheader("Running Metrics (default bout ≥2 s)")
        st.write(f"• Number of bouts: **{num_bouts}**")
        st.write(f"• Avg bout length: **{avg_length:.2f} s**")
        st.write(f"• Avg speed: **{avg_speed:.2f} m/min**")
        st.write(f"• Max speed: **{max_speed:.2f} m/min**")
        st.write("• Bout duration distribution:", bins)
        
        # Save into session for Step 2
        st.session_state.running_df       = running_data
        st.session_state.running_assessed = True

# ─── Step 2: Set Parameters & Upload Dopamine ──────────────────────────────────
if st.session_state.get("running_assessed", False):
    st.header("2) Set Analysis Parameters")
    running_bout_length   = st.slider("Minimum Running Bout Length (s)",        1, 60, 1)
    sedentary_bout_length = st.slider("Sedentary Bout Window (s)",             1, 60, 20)
    pre_running_seconds   = st.slider("Seconds Before Bout to Analyze",        0, 60, 5)
    post_running_seconds  = st.slider("Seconds After Bout to Analyze",         0, 60, 5)
    pre_offset_seconds    = st.slider("Seconds Before Bout End to Analyze",    0, 60, 5)

    dopamine_file = st.file_uploader("3) Upload Dopamine Data File", type=["xlsx"], key="dop_file")

    if dopamine_file and st.button("4) Analyze Everything"):
        # Retrieve the assessed running data
        running_data = st.session_state.running_df

        # Load & tag dopamine data
        dopamine_data = pd.read_excel(dopamine_file)
        dopamine_data.columns = dopamine_data.columns.str.strip()
        dopamine_data['file'] = os.path.basename(dopamine_file.name)
        if 'Time' in dopamine_data.columns:
            dopamine_data.rename(columns={'Time': 'Time (seconds)'}, inplace=True)

        # Compute avg dopamine per second
        dopamine_per_second = {}
        max_t = int(dopamine_data['Time (seconds)'].max())
        for sec in range(max_t + 1):
            subset = dopamine_data[
                (dopamine_data['Time (seconds)'] >= sec) &
                (dopamine_data['Time (seconds)'] <  sec + 1)
            ]
            if not subset.empty:
                dopamine_per_second[sec] = (
                    subset['Concentration'].mean(),
                    subset['file'].iloc[0]
                )
            else:
                dopamine_per_second[sec] = (np.nan, None)

        dopamine_df = pd.DataFrame.from_dict(
            dopamine_per_second, orient='index',
            columns=['Avg Dopamine Concentration', 'File Name']
        )
        dopamine_df.index.name = 'Time (seconds)'
        dopamine_df.reset_index(inplace=True)

        # Merge running + dopamine
        combined = pd.merge(
            running_data, dopamine_df,
            how='left', on='Time (seconds)'
        )
        combined['File Number'] = (combined.index // 60) + 1

        # Identify sedentary bouts
        sed_idxs = []
        for i in range(len(running_data)):
            if running_data['Average m/min'].iloc[i] == 0:
                start = max(0, i - sedentary_bout_length)
                end   = min(len(running_data) - 1, i + sedentary_bout_length)
                if all(running_data['Average m/min'].iloc[start:end+1] == 0):
                    sed_idxs.extend(range(start, end+1))
        sed_idxs = set(sed_idxs)
        combined['Sedentary Bout'] = combined['Time (seconds)'].apply(
            lambda x: 'Yes' if x in sed_idxs else 'No'
        )

        # Identify running bouts with user‑defined min length
        runs, current = [], []
        for i, spd in enumerate(running_data['Average m/min']):
            if spd > 0:
                current.append(i)
            else:
                if len(current) >= running_bout_length:
                    runs.append(current)
                current = []
        if len(current) >= running_bout_length:
            runs.append(current)

        # Collect dopamine around each bout
        before, after, offset, during = [], [], [], []
        for bout in runs:
            start, stop = bout[0], bout[-1]
            # before
            b = combined[
                (combined['Time (seconds)'] >= start - pre_running_seconds) &
                (combined['Time (seconds)'] <  start) &
                combined['Avg Dopamine Concentration'].notna() &
                (combined['Average m/min'] == 0)
            ]
            before.extend(b.values.tolist())
            # after
            a = combined[
                (combined['Time (seconds)'] >  stop) &
                (combined['Time (seconds)'] <= stop + post_running_seconds) &
                combined['Avg Dopamine Concentration'].notna() &
                (combined['Average m/min'] == 0)
            ]
            after.extend(a.values.tolist())
            # offset (during last pre_offset_seconds of bout)
            o = combined[
                (combined['Time (seconds)'] >= stop - pre_offset_seconds) &
                (combined['Time (seconds)'] <  stop) &
                combined['Avg Dopamine Concentration'].notna() &
                (combined['Average m/min'] > 0)
            ]
            offset.extend(o.values.tolist())
            # during
            d = combined[
                (combined['Time (seconds)'] >= start) &
                (combined['Time (seconds)'] <= stop) &
                combined['Avg Dopamine Concentration'].notna() &
                (combined['Average m/min'] > 0)
            ]
            during.extend(d.values.tolist())

        # Build DataFrames
        cols = combined.columns
        df_before = pd.DataFrame(before, columns=cols)
        df_after  = pd.DataFrame(after,  columns=cols)
        df_offset = pd.DataFrame(offset, columns=cols)
        df_during = pd.DataFrame(during, columns=cols)
        df_sed    = combined[combined['Time (seconds)'].isin(sed_idxs) & combined['Avg Dopamine Concentration'].notna()]

        # Offer an Excel download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            combined.to_excel(writer, sheet_name='Combined Data', index=False)
            df_during.to_excel(writer, sheet_name='Dopamine During', index=False)
            df_before.to_excel(writer, sheet_name='Dopamine Before', index=False)
            df_offset.to_excel(writer, sheet_name='Dopamine Offset', index=False)
            df_after.to_excel(writer, sheet_name='Dopamine After', index=False)
            df_sed.to_excel(writer, sheet_name='Sedentary Bouts', index=False)
        output.seek(0)

        st.success("All analyses complete!")
        st.download_button(
            label="Download Full Analysis Workbook",
            data=output,
            file_name="running_dopamine_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
