#!/usr/bin/env python3
"""
Data Analyzer Skill - Execution Script
Analyzes tabular data (CSV/JSON) with aggregation, filtering, and statistics.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

def read_csv(path: str) -> list[dict]:
    """Read CSV file and return list of dictionaries."""
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def read_json(path: str) -> list[dict]:
    """Read JSON file and return list of dictionaries."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'data' in data:
            return data['data']
        else:
            return [data]

def detect_format(path: str) -> str:
    """Detect file format based on extension."""
    ext = Path(path).suffix.lower()
    if ext in ['.csv']:
        return 'csv'
    elif ext in ['.json', '.ndjson']:
        return 'json'
    else:
        # Try CSV first, then JSON
        try:
            read_csv(path)
            return 'csv'
        except:
            try:
                read_json(path)
                return 'json'
            except:
                raise ValueError(f"Unsupported file format: {ext}")

def parse_numeric(value: str) -> float | None:
    """Try to parse a string as a number."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def aggregate_data(data: list[dict], group_by: str, operation: str, column: str) -> dict:
    """Aggregate data by group with specified operation."""
    groups = defaultdict(list)

    for row in data:
        key = row.get(group_by, 'unknown')
        val = parse_numeric(row.get(column, '0'))
        if val is not None:
            groups[key].append(val)

    results = {}
    for key, values in groups.items():
        if operation == 'sum':
            results[key] = sum(values)
        elif operation == 'avg':
            results[key] = sum(values) / len(values) if values else 0
        elif operation == 'count':
            results[key] = len(values)
        elif operation == 'min':
            results[key] = min(values) if values else 0
        elif operation == 'max':
            results[key] = max(values) if values else 0
        else:
            results[key] = sum(values)

    return results

def summarize_data(data: list[dict], columns: list[str] = None) -> dict:
    """Generate summary statistics for data."""
    if not data:
        return {"error": "No data"}

    if columns is None:
        columns = list(data[0].keys())

    summary = {}
    for col in columns:
        values = [parse_numeric(row.get(col, '0')) for row in data]
        values = [v for v in values if v is not None]

        if values:
            summary[col] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values)
            }
        else:
            # Text column
            text_values = [row.get(col, '') for row in data]
            unique = set(text_values)
            summary[col] = {
                "count": len(text_values),
                "unique": len(unique),
                "type": "text"
            }

    return summary

def filter_data(data: list[dict], column: str, operator: str, value: str) -> list[dict]:
    """Filter data based on condition."""
    filtered = []
    for row in data:
        row_val = row.get(column, '')
        num_row = parse_numeric(row_val)
        num_filter = parse_numeric(value)

        if operator == '=':
            if row_val == value or (num_row is not None and num_filter is not None and num_row == num_filter):
                filtered.append(row)
        elif operator == '>':
            if num_row is not None and num_filter is not None and num_row > num_filter:
                filtered.append(row)
        elif operator == '<':
            if num_row is not None and num_filter is not None and num_row < num_filter:
                filtered.append(row)
        elif operator == '>=':
            if num_row is not None and num_filter is not None and num_row >= num_filter:
                filtered.append(row)
        elif operator == '<=':
            if num_row is not None and num_filter is not None and num_row <= num_filter:
                filtered.append(row)
        elif operator == '!=':
            if row_val != value:
                filtered.append(row)

    return filtered

def main():
    """Main execution function."""
    # Read input from stdin
    input_data = sys.stdin.read().strip()
    if not input_data:
        input_data = '{}'

    try:
        params = json.loads(input_data)
    except json.JSONDecodeError:
        params = {}

    task = params.get('task', 'summarize')
    data_path = params.get('data_path', '')
    columns = params.get('columns', [])
    group_by = params.get('group_by', '')
    operation = params.get('operation', 'sum')
    output_format = params.get('output_format', 'json')

    if not data_path:
        result = {"error": "data_path is required"}
        print(json.dumps(result, ensure_ascii=False))
        return

    # Check if file exists
    if not Path(data_path).exists():
        result = {"error": f"File not found: {data_path}"}
        print(json.dumps(result, ensure_ascii=False))
        return

    # Read data
    try:
        fmt = detect_format(data_path)
        if fmt == 'csv':
            data = read_csv(data_path)
        else:
            data = read_json(data_path)
    except Exception as e:
        result = {"error": f"Failed to read file: {str(e)}"}
        print(json.dumps(result, ensure_ascii=False))
        return

    # Execute task
    result = {}
    try:
        if task == 'summarize':
            result = summarize_data(data, columns if columns else None)
        elif task == 'aggregate':
            if not group_by or not columns:
                result = {"error": "group_by and columns are required for aggregation"}
            else:
                for col in columns:
                    result[col] = aggregate_data(data, group_by, operation, col)
        elif task == 'filter':
            filter_column = params.get('filter_column', '')
            filter_operator = params.get('filter_operator', '=')
            filter_value = params.get('filter_value', '')
            if not filter_column:
                result = {"error": "filter_column is required for filter task"}
            else:
                filtered = filter_data(data, filter_column, filter_operator, filter_value)
                result = {"count": len(filtered), "data": filtered[:100]}  # Limit to 100 rows
        elif task == 'count':
            result = {"total_rows": len(data), "columns": list(data[0].keys()) if data else []}
        else:
            result = {"error": f"Unknown task: {task}"}
    except Exception as e:
        result = {"error": f"Analysis failed: {str(e)}"}

    # Output result
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
