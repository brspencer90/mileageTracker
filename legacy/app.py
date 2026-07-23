# %%
import pyodbc
import pandas as pd
import numpy as np
import streamlit as st
from constants import Constants as c
from mileage_func import get_data, push_data

# %%
df = get_data()
mileage_max = df['Mileage'].max()

st.dataframe(df,hide_index=True,use_container_width=True)

with st.sidebar:
    car = st.selectbox(
            label='Car',
            options=df['Car'].unique(),
            index=0
    )

    date = st.date_input(
            label='Date',
            value='today',
            format='YYYY-MM-DD'
    )

    mileage = st.number_input(
            label='Mileage',
            min_value=int(mileage_max),

    )

    gallons = st.number_input(
            label='Gallons',
            min_value=0.0,
            max_value=13.0
    )

    cost = st.number_input(
            label='Cost',
            min_value=0.0,
    )

    gas_station = st.text_input(
            label='Gas Station'
    )

    zipcode = st.text_input(
            label='Zip Code',
            max_chars = 5
    )

    missed_last = st.checkbox(
            label='Missed Last Fill',
            value=False
    )
    mpf = mileage - mileage_max
    mpg = round((mileage - mileage_max)/gallons,1)

    button_bool = ((len(gas_station) > 0) & \
                    (len(zipcode) == 5) & \
                    (cost > 0) & \
                    (gallons > 0) & \
                    (mileage > mileage_max))

    if st.button('Push to database',disabled=not button_bool):

        data_list = [car,date,mileage,gallons,cost,gas_station,zipcode,missed_last,mpf,mpg] 
        
        push_data(data_list)

        st.rerun()

    st.write('***')
    st.write(f'### **Miles since last fill :** {mpf} mi')

    st.write(f'### **Fuel economy :** {mpg} mpg')


    # %%
