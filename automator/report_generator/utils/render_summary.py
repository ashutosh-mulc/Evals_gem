import os
import uuid
import base64
from io import BytesIO
from pathlib import Path
from typing import Optional, Union
from PIL import Image
from collections import defaultdict
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import json
import pandas as pd
import numpy as np
import random
import hashlib

def hash_base64_image(b64_image: str, method: str = "sha256") -> str:
    """
    Compute a hash of a base64-encoded image.

    Args:
        b64_image (str): The base64-encoded image string.
        method (str): Hashing method ('sha256', 'md5', 'sha1', etc.).

    Returns:
        str: Hexadecimal hash string.
    """
    try:
        # Decode the base64 image to bytes
        image_bytes = base64.b64decode(b64_image)

        # Choose hash method
        hash_func = getattr(hashlib, method.lower())  # e.g., hashlib.sha256
        hash_digest = hash_func(image_bytes).hexdigest()
        return hash_digest
    except Exception as e:
        raise ValueError(f"Invalid base64 string or unknown hash method '{method}': {e}")
        
                
def snake_to_title_case(snake_str: str) -> str:
    """
    Convert a snake_case string to Snake Case (space-separated and capitalized).

    Args:
        snake_str (str): Input in snake_case format.

    Returns:
        str: Converted string in Snake Case.
    """
    words = snake_str.strip().split('_')
    return ' '.join(word.capitalize() for word in words if word)
    
    
class SummaryRenderer:
    def __init__(self, jsonl_path:str, output_dir: str = "output/summary_report", title="AI Evaluation Report"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        headers, self.records =  self.load_jsonl(jsonl_path)
        self.title = title
        self.VERSION = headers["version"]
        self.env = Environment(loader=FileSystemLoader(searchpath=str(Path(__file__).parent)))
        self.template = self.env.from_string(self._get_template())

    
    def load_jsonl(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        header = json.loads(lines[0])
        samples = [json.loads(line) for line in lines[1:]]
        return header, samples
    
    
    def write_report(self):
        summary = self._compute_summary()
        html = self.template.render(
            records=self.records,
            title=self.title,
            version=self.VERSION,
            timestamp=str(datetime.now()),
            summary=summary
        )
        with open(self.output_dir / "report.html", "w", encoding="utf-8") as f:
            f.write(html)

    def _compute_summary(self):
        # summary[metric][qtype] = list of values
        summary = defaultdict(lambda: defaultdict(list))
        system_error_count = 0
        image_to_rating = {}
        power_values = []
        print(type(self.records))
        for _rec in self.records:
            rec = _rec[0]
            image_key = hash_base64_image(rec["image"]) 
            qtype = rec["question_type"]
            rating =  rec["rating"]
            error_type = str(rec["error_type"])  
            if error_type == "not_english":
                 error_type == "non_unicode"      
            if rating == "N/A":
                summary[error_type]["ALL"].append(1.0)
                continue
            rating = float(rating)
            
            if qtype != "Memory Evaluation":
                if image_key in image_to_rating:
                    image_to_rating[image_key] += [rating]
                else:
                    image_to_rating[image_key] = [rating]
                  
            response_time = float(rec["response_time"])  if rec['response_time'] is not None else None
            summary["rating"][qtype].append(rating)
            summary["rating"]["ALL"].append(rating)
            summary["response_time"]["ALL"].append(response_time)
            summary[error_type]["ALL"].append(1.0)
            
            # Collect power values from meta_info
            pm = rec.get("meta_info", {}).get("power_metrics") or {}
            if pm.get("avg_power_w") is not None:
                power_values.append(float(pm["avg_power_w"]))

        multi_turn_ratings = []
        multi_turn_images = 0
        for k, v in  image_to_rating.items():
            multi_turn_ratings += v
            multi_turn_images += len(v)
            
       
        # Flatten to rows
        summary_rows = []
        
        sorted_summary=["rating","not_english","response_time","no_error","empty_response","json_decode_error"]
        for summary_item in sorted_summary:
            if summary_item not in summary:
                continue
            metric, qtype_dict = summary_item, summary[summary_item]
            if metric == "rating":
                for qtype, vals in qtype_dict.items():
                    non_binary = [ val for val in vals if val < 5 and val > 0]
                    if qtype != "ALL":
                        summary_rows.append({
                            #"metric": metric,
                            "metric_type": qtype,
                            "count": len(vals),
                            "average": round(sum(vals)/len(vals), 2)
                        })
            elif metric == "response_time":
                for qtype, vals in qtype_dict.items():
                    if qtype == "ALL":
                        count =  len([val for val in vals if val is not None])
                        mean_response_time = 0
                        if count == 0:
                            mean_response_time = None
                        else:
                            mean_response_time = round(sum([val for val in vals if val is not None])/count, 2)
                        summary_rows.append({
                            #"metric": metric,
                            "metric_type": snake_to_title_case(metric),
                            "count": count,
                            "average": mean_response_time
                        })
                        
            elif metric == "no_error":
                for qtype, vals in qtype_dict.items():
                    if qtype == "ALL":
                        summary_rows.append({
                            #"metric": metric,
                            "metric_type": "Error Rate",
                            "count": len(vals),
                            "average": round(100 - (100*sum(vals))/len(self.records), 2)
                        })
                        
            else:
                for qtype, vals in qtype_dict.items():
                    if qtype == "ALL":
                        summary_rows.append({
                            #"metric": metric,
                            "metric_type": snake_to_title_case(metric),
                            "count": len(vals),
                            "average": round((100*sum(vals))/len(self.records), 2)
                        })
        if len(multi_turn_ratings) > 0:                
            summary_rows.append({
                #"metric": metric,
                "metric_type": "Multi Turn Metric",
                "count": multi_turn_images,
                "average": round(sum(multi_turn_ratings)/len(multi_turn_ratings), 2)
            })
        
        # Add power summary row
        if power_values:
            summary_rows.append({
                "metric_type": "Avg Power (W)",
                "count": len(power_values),
                "average": round(sum(power_values) / len(power_values), 3),
            })
                
        return summary_rows

    def _get_template(self):
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>{{ title }}</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background: #f4f6f9; }
                .entry { background: white; border-radius: 10px; padding: 16px; margin-bottom: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
                .image { max-width: 300px; display: block; margin-bottom: 10px; }
                audio { margin-top: 8px; }
                .error { color: red; font-weight: bold; }
                .question, .reference, .transcribed, .meta { margin-bottom: 6px; }
                h1 { margin-bottom: 10px; }
                h2 { margin-top: 40px; }
                table { border-collapse: collapse; width: 80%; margin-bottom: 30px; }
                th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
                th { background-color: #e9ecef; }
                .metric { font-size: 1em; margin-top: 5px; }
                .reasoning { font-style: italic; font-size: 0.9em; color: #444; }
            </style>
        </head>
        <body>
            <h1>{{ title }}</h1>
            <p><strong>Generated:</strong> {{ timestamp }} | <strong>Version:</strong> {{ version }}</p>

            <h2>Metric Summary</h2>
            <table>
                <tr><th>Type</th><th>Count</th><th>Average</th></tr>
                {% for row in summary %}
                    <tr>
                        <td>{{ row.metric_type }}</td>
                        <td>{{ row.count }}</td>
                        <td>{{ '-' if row.average is none else row.average }}</td>
                    </tr>
                {% endfor %}
            </table>    
        </body>
        </html>
        """
