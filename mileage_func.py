# %%
import pyodbc
from constants import Constants as c
from dotenv import load_dotenv
from os import environ
from datetime import datetime as dt

import pandas as pd

# Create database connection
def GetPYODBCConnection():
    return pyodbc.connect(f'DRIVER={c.ODBCDRIVER};{GetConnectionString()};TrustServerCertificate=Yes')

def GetConnectionString():
    load_dotenv()
    return environ[c.ENV_CONNECTION_STRING]

def parse_csv():
    cnxn = GetPYODBCConnection()
    cursor = cnxn.cursor()

    dict_col = dict(zip(
        ['Car','Date','Mileage','Gallons','Cost','Gas Station','Zip code','Missed Last Fill', 'MPF','MPG'],
        [str,str,float,float,float,str,str,float,float,float]))

    df = pd.read_csv('mileageTracker.csv',dtype=dict_col,keep_default_na=True,na_values='#N/A')

    for idx in range(len(df)):
        
        line = tuple(df.loc[idx,:].replace({np.nan:None}).values)

        col_list = ', '.join(c.LIST_MILE_COL)
        q_list = ', '.join('?'*len(c.LIST_MILE_COL))

        query = f'INSERT INTO {c.DB_NAME} ({col_list}) values ({q_list})'

        cursor.execute(query,line)

    cursor.commit()
    cnxn.close()

def get_data():
    cnxn = GetPYODBCConnection()

    query = 'SELECT * FROM mileage'

    df = pd.read_sql(query,cnxn).sort_values('mileage',ascending=False).reset_index(drop=True)
    df.columns = c.LIST_READ_COL

    df['Date'] = df['Date'].dt.date
    df['Zip Code'] = df['Zip Code'].apply(lambda x: f'{x:.0f}').astype(str)
    df['Missed Last Fill'] = df['Missed Last Fill'].astype(bool)  

    return df

def push_data(data_list):
    cnxn = GetPYODBCConnection()
    cursor = cnxn.cursor() 

    col_list = ', '.join(c.LIST_MILE_COL)
    q_list = ', '.join('?'*len(c.LIST_MILE_COL))

    query = f'INSERT INTO {c.DB_NAME} ({col_list}) values ({q_list})'

    cursor.execute(query,data_list)

    cursor.commit()
    cnxn.close()

