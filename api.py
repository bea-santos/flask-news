#!/usr/bin/python

import json
import requests
import numpy as np
import pandas as pd
import geopandas as gpd
from datetime import datetime as dt
from pytrends.request import TrendReq 
from flask import Flask, render_template, Markup
from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.palettes import brewer
from bokeh.models import HoverTool, LinearColorMapper, ColorBar, GeoJSONDataSource
import logging 
import sys

'''
Create an app object - instance of the Flask object
It'll act as the central configuration object for the entire application.
It's used to set up pieces of the application required for extended functionality
used to set up the routes that will become the application's points of interaction
'''
app = Flask(__name__) 


'''
the decorator is telling our @app that 
whenever a user visits our app domain 
at the given .route(), execute the index() function
'''

@app.route('/')
def index():
    mylist = get_newsapi_data()
    script, div = google_trends_interest_over_time()
    #script2, div2 = google_trends_interest_by_region()
    return render_template('index.html', context = mylist, script=script, div=div)


@app.route('/region')
def region():
    script2, div2 = google_trends_interest_by_region()
    return render_template('region.html', script2=script2, div2=div2)



@app.route('/errors')
def errors():  

    now = dt.today().strftime("%m-%d-%Y")
    filename = "info_" + str(now) + ".log" 

    file_logging(filename)
    mylist = service_logs(filename)
    
    return render_template('errors.html', mylist=mylist)



def get_newsapi_data():
    api_key = 'd7b2b73bffae4ad89ca895ae788e81cf'
    url = 'https://newsapi.org/v2/top-headlines' # Define the endpoint
    parameters = {
        'q': 'stock market',
        'pageSize': 20, 
        'apiKey': api_key 
    }

    response = requests.get(url, params=parameters)

    '''
    try:
        response = requests.get(url, params=parameters) # Make the request
    except requests.exceptions.Timeout:
        # Maybe set up for a retry, or continue in a retry loop
        response = None
    except requests.exceptions.ConnectionError:
        # Network connection failed
        pass
    except requests.exceptions.TooManyRedirects:
        # Tell the user their URL was bad and try a different one
        pass
    except requests.exceptions.RequestException as e:
        # catastrophic error. bail.
        raise SystemExit(e)
    '''
    
    response_json = response.json()
    articles = response_json['articles']
    author = []
    title = []
    desc = []
    publishedAt = []
    img = []

    for i in range(len(articles)):
        myarticles = articles[i]
        author.append(myarticles['author'])
        title.append(myarticles['title'])
        desc.append(myarticles['description'])
        publishedAt.append(pd.to_datetime(myarticles['publishedAt']).date())
        img.append(myarticles['urlToImage'])

    mylist = zip(author, title, desc, publishedAt, img)
    return mylist



def connect_to_google():
    response =  TrendReq(hl='en-US', tz=360)
    keywords = ['Coronavirus', 'Stock market']
    response.build_payload(kw_list = keywords, cat = 0, timeframe = 'today 3-m', geo = '', gprop = '')
    return response


def google_trends_interest_over_time():
    response = connect_to_google()    
    
    df = response.interest_over_time()
    df = df.drop(labels=['isPartial'],axis='columns') # completeness of the data point for that date
    df['date'] = df.index.values
    df['year'] = pd.DatetimeIndex(df['date']).year
    df['month'] = pd.DatetimeIndex(df['date']).month

    labels = df['date'].values
    values1 = df['Coronavirus'].values #/ df['Coronavirus'].values.max()
    values2 = df['Stock market'].values #/ df['Stock market'].values.max()


    TOOLS = "hover,save,pan,box_zoom,reset,wheel_zoom,crosshair"
    p = figure( y_axis_type="linear", 
                x_axis_type='datetime', 
                tools = TOOLS,
                background_fill_color=None,
                border_fill_color = None,
                plot_height = 350, 
                plot_width = 950)

    p.yaxis.axis_label = 'Google Trend'
    p.yaxis.axis_label_text_color = "white"
    p.select_one(HoverTool).tooltips = [
        ('Date', '@x{%F}'),
        ('Interest', '@y')
    ]

    p.select_one(HoverTool).formatters = {
        "@x": "datetime"
    }

    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None
    p.line(labels, values1, legend_label="Coronavirus", line_color="red", line_width = 3)
    p.line(labels, values2, legend_label="Stock market", line_color="deepskyblue", line_width = 3)

    p.legend.location = "top_left"
    p.legend.background_fill_alpha = None
    p.outline_line_color = None
    p.legend.label_text_color = "white"
    p.legend.border_line_color = None
    p.toolbar.autohide = True
    p.axis.axis_line_color = "white"
    p.axis.major_label_text_color = "white"
    p.axis.minor_tick_line_color = None
    p.axis.major_tick_line_color = "white"

    script, div = components(p)
    return script, div


def google_trends_interest_by_region():
    response = connect_to_google()

    #fetch google data 
    df_google = response.interest_by_region(resolution='', inc_low_vol=True, inc_geo_code=True)
    df_google = df_google.rename({'United States':'United States of America'})
    df_google = df_google.reset_index()
    df_google.rename(columns = {'geoName':'Country'}, inplace = True) 

    # read shapes - attributes of geographic features
    shapefile = 'geo/ne_110m_admin_0_countries.shp'
    geo = gpd.read_file(shapefile)[['ADMIN', 'ADM0_A3', 'geometry']]
    geo.columns = ['Country', 'geoCode', 'geometry']
    geo = geo.loc[~(geo['Country'] == 'Antarctica')]
    geo = geo.loc[~(geo['Country'] == 'North Korea')]

    # Merge the geographic data with obesity data
    df_merged = geo.merge(df_google, on='Country', how='left')
    low = df_merged['Coronavirus'].min()
    high = df_merged['Coronavirus'].max()
    df_merged.fillna('No data', inplace = True)

    # Input sources
    # source that will contain all necessary data for the map
    geosource = GeoJSONDataSource(geojson=df_merged.to_json())
    # source that contains the data that is actually shown on the map (for a given year)
    displayed_src = GeoJSONDataSource(geojson=df_merged.to_json())

    palette = brewer['OrRd'][8]
    palette = palette[::-1]
    countries = sorted(df_merged[df_merged["Coronavirus"] != "No data"]["Country"].unique())

    #Instantiate LinearColorMapper that linearly maps numbers in a range, into a sequence of colors.
    color_mapper = LinearColorMapper(palette = palette, low = low, high = high)
    color_bar = ColorBar(color_mapper=color_mapper, 
                         label_standoff=8, 
                         width=9, height=220,
                         location=(0,0), 
                         orientation='vertical', 
                         major_label_text_color = 'white',
                         background_fill_color=None)

    tools = 'wheel_zoom,pan,reset'
    p = figure(tools=tools,
               toolbar_location='right',
               background_fill_color=None,
               border_fill_color = None,
               plot_height = 370, 
               plot_width = 860
               )

    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None

    #Add patch renderer to figure
    p.patches('xs','ys', source=displayed_src, fill_alpha=1, line_width=0.5, line_color='black',
              fill_color={'field' :'Coronavirus', 'transform': color_mapper})
    p.add_layout(color_bar, 'center')

    # hover tool for the map
    map_hover = HoverTool(tooltips=[
        ('Country','@Country'),
        ('Coronavirus Interest', '@Coronavirus')
    ])

    # Add hover tool
    p.add_tools(map_hover)

    p.outline_line_color = None
    p.toolbar.autohide = True
    p.axis.axis_line_color = None
    p.axis.major_label_text_color = None
    p.axis.minor_tick_line_color = None
    p.axis.major_tick_line_color = None

    script, div = components(p)
    return script, div 





def service_logs(filename):
    fields = ['time', 'thread', 'level', 'message']

    df = pd.read_csv(filename, error_bad_lines=False, header=None)
    df.columns = fields
    
    time=df['time']
    thread = df['thread']
    level = df['level']
    message = df['message']

    mylist = zip(time, thread, level, message)
    return mylist

def file_logging(filename):
    logFormatter = logging.Formatter("%(asctime)s, %(threadName)-12.12s, %(levelname)-5.5s, %(message)s", "%Y-%m-%d %H:%M:%S")
    rootLogger = logging.getLogger()


    fileHandler = logging.FileHandler(filename, encoding='utf-8')
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


if __name__ == "__main__":
    app.run(debug=True)
    



