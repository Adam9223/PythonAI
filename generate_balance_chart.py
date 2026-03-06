#!/usr/bin/env python3
import json
import os

# Load GL data
if os.path.exists('gl_sample_data.json'):
    with open('gl_sample_data.json', 'r') as f:
        gl_data = json.load(f)
    
    if 'samples' in gl_data and 'annual_trend' in gl_data['samples']:
        trend_data = gl_data['samples']['annual_trend']
        rep = trend_data.get('rep', [])
        
        if rep and len(rep) > 0:
            # Extract data for line chart visualization
            labels = [item['YrMo'] for item in rep]
            balance_data = [item['runBal'] for item in rep]
            
            chart_data = {
                'type': 'chart',
                'chartType': 'line',
                'title': "General Ledger - Running Balance",
                'chartData': {
                    'labels': labels,
                    'datasets': [
                        {
                            'label': 'Running Balance',
                            'data': balance_data,
                            'borderColor': 'rgba(255, 140, 0, 1)',
                            'backgroundColor': 'rgba(255, 140, 0, 0.1)',
                            'tension': 0.4
                        }
                    ]
                }
            }
            
            print(json.dumps(chart_data, indent=2))
