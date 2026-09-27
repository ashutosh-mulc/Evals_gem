import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

def render_part_html(header, samples, output_path: str):
    env = Environment(loader=FileSystemLoader("automator/templates"))
    template = env.get_template("response_visualizer.html")
    output_html = template.render(header=header, samples=samples)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_html)
        
def render_dataset(header, samples, output_path: str):
    env = Environment(loader=FileSystemLoader("automator/templates"))
    template = env.get_template("dataset_visualizer.html")
    output_html = template.render(header=header, samples=samples)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_html)