import json, os, shutil, glob, tqdm, sys
import numpy as np

def generate_combined_report(part_reports, out_folder):
    header = [json.loads(x) for x in open(part_reports[0], 'r').read().strip().split("\n")][0]

    jsonlines = []
    for file in part_reports:
        lines = [json.loads(x) for x in open(file, 'r').read().strip().split("\n")][1:]
        jsonlines += lines
    
    out_file = open(os.path.join(out_folder, "vqa_report_baseline.jsonl"), 'w')

    out_file.write(json.dumps(header) + "\n")
    for line in jsonlines:
        out_file.write(json.dumps(line) + "\n")
    out_file.close()

if __name__ == '__main__':
    part_reports = []            
    generate_combined_report([
    "/home/test/Amartya/work_2026/Gemini_Live_Evaluation/Evaluation_Framework/data/results/jinju_gemini_denoised_0705_0_25/vqa_report.jsonl",
    "/home/test/Amartya/work_2026/Gemini_Live_Evaluation/Evaluation_Framework/data/results/jinju_gemini_denoised_0705_25_75/vqa_report.jsonl",
    "/home/test/Amartya/work_2026/Gemini_Live_Evaluation/Evaluation_Framework/data/results/jinju_gemini_denoised_0705_100_50/vqa_report.jsonl"],
    "data/results/jinju_gemini_denoised_0705_0_150")
