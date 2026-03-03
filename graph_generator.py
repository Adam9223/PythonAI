"""
Graph Generation Module
Generates various types of charts and graphs based on data
"""

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import json
import os
import io
import base64
from typing import Dict, List, Union, Optional
from datetime import datetime


class GraphGenerator:
    """Generate various types of graphs and charts"""
    
    def __init__(self, output_dir: str = "graphs", show_graphs: bool = True):
        """
        Initialize the graph generator
        
        Args:
            output_dir: Directory to save generated graphs
            show_graphs: Whether to display graphs in GUI window
        """
        self.output_dir = output_dir
        self.show_graphs = show_graphs
        os.makedirs(output_dir, exist_ok=True)
        
        # Set backend based on mode
        if not show_graphs:
            matplotlib.use('Agg')  # Non-interactive backend for server
        
        # Set style for better-looking graphs
        try:
            plt.style.use('seaborn-v0_8-darkgrid')
        except:
            plt.style.use('default')
    
    def generate_line_chart(self, 
                           data: Dict[str, List[float]], 
                           title: str = "Line Chart",
                           xlabel: str = "X Axis",
                           ylabel: str = "Y Axis",
                           filename: str = None,
                           show: bool = None) -> str:
        """
        Generate a line chart
        
        Args:
            data: Dictionary with labels as keys and lists of values
            title: Chart title
            xlabel: X-axis label
            ylabel: Y-axis label
            filename: Optional custom filename
            show: Override default show_graphs setting
            
        Returns:
            Path to the saved graph image or "displayed" if only shown
        """
        if show is None:
            show = self.show_graphs
            
        fig, ax = plt.subplots(figsize=(10, 6))
        
        for label, values in data.items():
            ax.plot(values, marker='o', label=label)
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if not filename:
            filename = f"line_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return filepath
    
    def generate_bar_chart(self,
                          data: Dict[str, float],
                          title: str = "Bar Chart",
                          xlabel: str = "Categories",
                          ylabel: str = "Values",
                          filename: str = None,
                          show: bool = None) -> str:
        """
        Generate a bar chart
        
        Args:
            data: Dictionary with categories as keys and values
            title: Chart title
            xlabel: X-axis label
            ylabel: Y-axis label
            filename: Optional custom filename
            show: Override default show_graphs setting
            
        Returns:
            Path to the saved graph image or "displayed" if only shown
        """
        if show is None:
            show = self.show_graphs
            
        fig, ax = plt.subplots(figsize=(10, 6))
        
        categories = list(data.keys())
        values = list(data.values())
        
        bars = ax.bar(categories, values, color='steelblue', alpha=0.8)
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.1f}',
                   ha='center', va='bottom', fontsize=10)
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        
        if not filename:
            filename = f"bar_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return filepath
    
    def generate_pie_chart(self,
                          data: Dict[str, float],
                          title: str = "Pie Chart",
                          filename: str = None,
                          show: bool = None) -> str:
        """
        Generate a pie chart
        
        Args:
            data: Dictionary with labels as keys and values
            title: Chart title
            filename: Optional custom filename
            show: Override default show_graphs setting
            
        Returns:
            Path to the saved graph image or "displayed" if only shown
        """
        if show is None:
            show = self.show_graphs
            
        fig, ax = plt.subplots(figsize=(10, 8))
        
        labels = list(data.keys())
        sizes = list(data.values())
        
        # Create pie chart
        wedges, texts, autotexts = ax.pie(
            sizes, 
            labels=labels, 
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontsize': 10}
        )
        
        # Make percentage text bold
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        
        plt.tight_layout()
        
        if not filename:
            filename = f"pie_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return filepath
    
    def generate_scatter_plot(self,
                             x_data: List[float],
                             y_data: List[float],
                             title: str = "Scatter Plot",
                             xlabel: str = "X Axis",
                             ylabel: str = "Y Axis",
                             filename: str = None,
                             show: bool = None) -> str:
        """
        Generate a scatter plot
        
        Args:
            x_data: List of x values
            y_data: List of y values
            title: Chart title
            xlabel: X-axis label
            ylabel: Y-axis label
            filename: Optional custom filename
            show: Override default show_graphs setting
            
        Returns:
            Path to the saved graph image or "displayed" if only shown
        """
        if show is None:
            show = self.show_graphs
            
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.scatter(x_data, y_data, alpha=0.6, s=100, color='steelblue')
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if not filename:
            filename = f"scatter_plot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return filepath
    
    def generate_histogram(self,
                          data: List[float],
                          title: str = "Histogram",
                          xlabel: str = "Value",
                          ylabel: str = "Frequency",
                          bins: int = 30,
                          filename: str = None) -> str:
        """
        Generate a histogram
        
        Args:
            data: List of values
            title: Chart title
            xlabel: X-axis label
            ylabel: Y-axis label
            bins: Number of bins
            filename: Optional custom filename
            
        Returns:
            Path to the saved graph image
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.hist(data, bins=bins, color='steelblue', alpha=0.7, edgecolor='black')
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        if not filename:
            filename = f"histogram_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        
        return filepath
    
    def generate_from_table(self,
                           table_data: List[List[str]],
                           chart_type: str = "bar",
                           title: str = "Chart from Table",
                           filename: str = None) -> str:
        """
        Generate a chart from table data (typically from web scraping)
        
        Args:
            table_data: 2D list representing a table (first row as headers)
            chart_type: Type of chart ('bar', 'line', 'pie')
            title: Chart title
            filename: Optional custom filename
            
        Returns:
            Path to the saved graph image
        """
        if len(table_data) < 2:
            raise ValueError("Table must have at least headers and one data row")
        
        # Create DataFrame from table
        df = pd.DataFrame(table_data[1:], columns=table_data[0])
        
        # Try to convert numeric columns
        for col in df.columns[1:]:
            try:
                df[col] = pd.to_numeric(df[col].str.replace(',', ''))
            except:
                pass
        
        # Generate chart based on type
        if chart_type == "bar":
            data = {row[0]: float(row[1]) for row in table_data[1:] if len(row) >= 2}
            return self.generate_bar_chart(data, title=title, filename=filename)
        
        elif chart_type == "line":
            data = {}
            for col in df.columns[1:]:
                try:
                    data[col] = df[col].astype(float).tolist()
                except:
                    pass
            return self.generate_line_chart(data, title=title, filename=filename)
        
        elif chart_type == "pie":
            data = {row[0]: float(row[1]) for row in table_data[1:] if len(row) >= 2}
            return self.generate_pie_chart(data, title=title, filename=filename)
        
        else:
            raise ValueError(f"Unsupported chart type: {chart_type}")


# Example usage
if __name__ == "__main__":
    generator = GraphGenerator()
    
    # Example: Bar chart
    data = {"Product A": 150, "Product B": 200, "Product C": 120, "Product D": 180}
    path = generator.generate_bar_chart(data, title="Product Sales")
    print(f"Bar chart saved to: {path}")
    
    # Example: Line chart
    data = {
        "Series 1": [10, 15, 13, 17, 20, 22],
        "Series 2": [12, 11, 14, 16, 19, 21]
    }
    path = generator.generate_line_chart(data, title="Trends Over Time")
    print(f"Line chart saved to: {path}")
    
    # Example: Pie chart
    data = {"Category A": 30, "Category B": 25, "Category C": 20, "Category D": 25}
    path = generator.generate_pie_chart(data, title="Market Share")
    print(f"Pie chart saved to: {path}")
