#!/usr/bin/env python3
"""
从AISBench测试日志目录中提取第二次测试（全量数据集测试）的性能指标
"""

import os
import re
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class LogParser:
    """解析AISBench测试日志"""
    
    def __init__(self, log_file_path: str):
        self.log_file = log_file_path
        self.content = ""
        self._load_log()
    
    def _load_log(self):
        """加载日志文件"""
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                self.content = f.read()
        except Exception as e:
            print(f"读取日志文件失败: {e}")
    
    def parse_second_test_json(self) -> Optional[Dict]:
        """
        提取第二次测试的JSON结果
        从日志中查找 output_len > 1 的JSON结果
        """
        # 查找所有JSON格式的性能结果
        json_pattern = r"\{'current_time':\s*'[^']+',\s*'input_len':\s*[\d.]+,.*?\}"
        json_matches = list(re.finditer(json_pattern, self.content, re.DOTALL))
        
        if not json_matches:
            json_pattern = r'\{[^{]*"current_time"[^}]*\}'
            json_matches = list(re.finditer(json_pattern, self.content, re.DOTALL))
        
        if not json_matches:
            json_pattern = r"\{'current_time':.*?\}"
            json_matches = list(re.finditer(json_pattern, self.content, re.DOTALL))
        
        if not json_matches:
            print(f"  未找到任何性能结果JSON")
            return None
        
        # 遍历所有JSON，找到 output_len > 1 的（第二次测试）
        for match in json_matches:
            json_str = match.group().replace("'", '"')
            try:
                result = json.loads(json_str)
                output_len = result.get('output_len', 0)
                if output_len > 1:
                    return result
            except json.JSONDecodeError:
                continue
        
        # 如果没找到 output_len > 1 的，取最后一个（通常是第二次测试）
        last_json = json_matches[-1].group().replace("'", '"')
        try:
            result = json.loads(last_json)
            return result
        except json.JSONDecodeError:
            return None
    
    def parse_second_test_perf_table(self) -> Dict:
        """
        提取第二次测试的性能表格指标
        通过查找 output_len=512 的测试对应的Performance Results
        """
        result = {}
        
        # 找到第二次测试的Performance Results表格
        # 特征：在 "全量数据集测试" 之后的 Performance Results
        full_test_pos = self.content.find("[开始] 全量数据集测试")
        if full_test_pos == -1:
            full_test_pos = self.content.find("全量数据集测试")
        
        if full_test_pos == -1:
            return result
        
        # 从 full_test_pos 之后查找 Performance Results
        after_content = self.content[full_test_pos:]
        
        # 查找 "Performance Results of task"
        perf_marker = "Performance Results of task"
        perf_pos = after_content.find(perf_marker)
        
        if perf_pos == -1:
            return result
        
        perf_content = after_content[perf_pos:]
        
        # 提取TTFT行
        ttft_pattern = r'TTFT\s+.*?total.*?([\d.]+)\s+ms.*?([\d.]+)\s+ms.*?([\d.]+)\s+ms'
        ttft_match = re.search(ttft_pattern, perf_content, re.DOTALL)
        if ttft_match:
            result['TTFT_avg'] = float(ttft_match.group(1))
            result['TTFT_min'] = float(ttft_match.group(2))
            result['TTFT_max'] = float(ttft_match.group(3))
        
        # 提取TPOT行
        tpot_pattern = r'TPOT\s+.*?total.*?([\d.]+)\s+ms.*?([\d.]+)\s+ms.*?([\d.]+)\s+ms'
        tpot_match = re.search(tpot_pattern, perf_content, re.DOTALL)
        if tpot_match:
            result['TPOT_avg'] = float(tpot_match.group(1))
            result['TPOT_min'] = float(tpot_match.group(2))
            result['TPOT_max'] = float(tpot_match.group(3))
        
        # 提取E2EL行
        e2el_pattern = r'E2EL\s+.*?total.*?([\d.]+)\s+ms.*?([\d.]+)\s+ms.*?([\d.]+)\s+ms'
        e2el_match = re.search(e2el_pattern, perf_content, re.DOTALL)
        if e2el_match:
            result['E2EL_avg'] = float(e2el_match.group(1))
            result['E2EL_min'] = float(e2el_match.group(2))
            result['E2EL_max'] = float(e2el_match.group(3))
        
        # 提取Common Metrics
        common_marker = "Common Metric"
        common_pos = perf_content.find(common_marker)
        if common_pos != -1:
            common_content = perf_content[common_pos:]
            
            # Prefill Token Throughput
            prefill_pattern = r'Prefill Token Throughput.*?([\d.]+)\s+token/s'
            prefill_match = re.search(prefill_pattern, common_content, re.DOTALL)
            if prefill_match:
                result['prefill_token_throughput'] = float(prefill_match.group(1))
            
            # Input Token Throughput
            input_pattern = r'Input Token Throughput.*?([\d.]+)\s+token/s'
            input_match = re.search(input_pattern, common_content, re.DOTALL)
            if input_match:
                result['input_token_throughput'] = float(input_match.group(1))
            
            # Output Token Throughput
            output_pattern = r'Output Token Throughput.*?([\d.]+)\s+token/s'
            output_match = re.search(output_pattern, common_content, re.DOTALL)
            if output_match:
                result['output_throughput'] = float(output_match.group(1))
            
            # Total Token Throughput
            total_pattern = r'Total Token Throughput.*?([\d.]+)\s+token/s'
            total_match = re.search(total_pattern, common_content, re.DOTALL)
            if total_match:
                result['E2E_throughput'] = float(total_match.group(1))
            
            # Request Throughput
            req_pattern = r'Request Throughput.*?([\d.]+)\s+req/s'
            req_match = re.search(req_pattern, common_content, re.DOTALL)
            if req_match:
                result['qps'] = float(req_match.group(1))
            
            # Concurrency
            conc_pattern = r'Concurrency\s+.*?([\d.]+)'
            conc_match = re.search(conc_pattern, common_content, re.DOTALL)
            if conc_match:
                result['cc'] = float(conc_match.group(1))
        
        return result
    
    def parse_hit_rates_second_test(self) -> Tuple[float, float]:
        """
        提取第二次测试的命中率
        """
        hbm_hit_rate = 0.0
        external_hit_rate = 0.0
        
        # 在 "全量数据集测试完成" 之后查找命中率
        full_test_pos = self.content.find("全量数据集测试完成，结果保存在aisbench_result.csv")
        if full_test_pos == -1:
            full_test_pos = self.content.find("全量数据集测试完成")
        
        if full_test_pos == -1:
            return self._parse_last_hit_rates()
        
        after_content = self.content[full_test_pos:]
        
        # 查找 Prefix cache hit summary
        hit_summary_pos = after_content.find("Prefix cache hit summary")
        if hit_summary_pos == -1:
            return self._parse_last_hit_rates()
        
        hit_section = after_content[hit_summary_pos:]
        
        # 从表格提取
        table_pattern = r'ALL_PODS\s+([\d.]+)%\s+[\d/]+\s+([\d.]+)%\s+[\d/]+'
        table_match = re.search(table_pattern, hit_section, re.DOTALL)
        if table_match:
            hbm_hit_rate = float(table_match.group(1))
            external_hit_rate = float(table_match.group(2))
            return hbm_hit_rate, external_hit_rate
        
        # 从 key-value 格式提取
        ext_pattern = r'external_hit_rate\s+([\d.]+)%'
        ext_match = re.search(ext_pattern, hit_section)
        if ext_match:
            external_hit_rate = float(ext_match.group(1))
        
        hbm_pattern = r'hbm_hit_rate\s+([\d.]+)%'
        hbm_match = re.search(hbm_pattern, hit_section)
        if hbm_match:
            hbm_hit_rate = float(hbm_match.group(1))
        
        return hbm_hit_rate, external_hit_rate
    
    def _parse_last_hit_rates(self) -> Tuple[float, float]:
        """解析最后一次出现的命中率"""
        hbm_hit_rate = 0.0
        external_hit_rate = 0.0
        
        hit_pattern = r"Prefix cache hit summary.*?ALL_PODS\s+([\d.]+)%\s+[\d/]+\s+([\d.]+)%\s+[\d/]+"
        matches = list(re.finditer(hit_pattern, self.content, re.DOTALL))
        
        if matches:
            last_match = matches[-1]
            hbm_hit_rate = float(last_match.group(1))
            external_hit_rate = float(last_match.group(2))
            return hbm_hit_rate, external_hit_rate
        
        return hbm_hit_rate, external_hit_rate
    
    def parse_basic_params(self) -> Dict:
        """从日志开头提取基本参数"""
        params = {}
        
        # 提取input_len
        input_pattern = r'input token length:\s*(\d+)'
        input_match = re.search(input_pattern, self.content)
        if input_match:
            params['input_len'] = float(input_match.group(1))
        
        # 提取output_len
        output_pattern = r'output token length:\s*(\d+)'
        output_match = re.search(output_pattern, self.content)
        if output_match:
            params['output_len'] = float(output_match.group(1))
        
        # 提取total_req
        data_pattern = r'number of dataset:\s*(\d+)'
        data_match = re.search(data_pattern, self.content)
        if data_match:
            params['total_req'] = float(data_match.group(1))
        
        # 提取max_cc
        conc_pattern = r'concurrency:\s*(\d+)'
        conc_match = re.search(conc_pattern, self.content)
        if conc_match:
            params['max_cc'] = float(conc_match.group(1))
        
        return params

def parse_single_log(log_file: str) -> Optional[Dict]:
    """解析单个日志文件，提取第二次测试的结果"""
    parser = LogParser(log_file)
    
    # 提取基本参数
    basic_params = parser.parse_basic_params()
    
    # 提取第二次测试的JSON结果
    json_result = parser.parse_second_test_json()
    
    if not json_result:
        return None
    
    # 提取第二次测试的性能表格
    perf_result = parser.parse_second_test_perf_table()
    
    # 提取命中率
    hbm_hit_rate, external_hit_rate = parser.parse_hit_rates_second_test()
    
    # 合并结果
    result = {}
    result.update(basic_params)
    result.update(json_result)
    result.update(perf_result)
    result['hbm_hit_rate'] = hbm_hit_rate
    result['external_hit_rate'] = external_hit_rate
    
    return result

def process_log_directory(log_dir: str, output_csv: str):
    """处理日志目录中的所有日志文件"""
    log_path = Path(log_dir)
    
    log_files = list(log_path.glob("test_*.log"))
    
    if not log_files:
        print(f"错误: 在 {log_dir} 中未找到 test_*.log 文件")
        return
    
    print(f"找到 {len(log_files)} 个日志文件")
    print("-" * 60)
    
    results = []
    
    for log_file in sorted(log_files):
        print(f"处理: {log_file.name}")
        result = parse_single_log(str(log_file))
        
        if result:
            row = {
                'input_len': result.get('input_len', ''),
                'output_len': result.get('output_len', ''),
                'total_req': result.get('total_req', ''),
                'max_cc': result.get('max_cc', ''),
                'cc': result.get('cc', ''),
                'hbm_hit_rate': result.get('hbm_hit_rate', 0),
                'external_hit_rate': result.get('external_hit_rate', 0),
                'TTFT_avg': result.get('TTFT_avg', ''),
                'TTFT_min': result.get('TTFT_min', ''),
                'TTFT_max': result.get('TTFT_max', ''),
                'TTFT_P90': result.get('TTFT P90', ''),
                'TPOT_avg': result.get('TPOT_avg', ''),
                'TPOT_min': result.get('TPOT_min', ''),
                'TPOT_max': result.get('TPOT_max', ''),
                'TPOT_SLO_P90': result.get('TPOT SLO_P90', ''),
                'E2E_time': result.get('E2E_time', ''),
                'output_throughput': result.get('output_throughput', ''),
                'E2E_throughput': result.get('E2E_throughput', ''),
                'qps': result.get('qps', ''),
                'qpm': result.get('qpm', ''),
                'input_token_throughput': result.get('input_token_throughput', ''),
                'prefill_token_throughput': result.get('prefill_token_throughput', ''),
                'E2EL_avg': result.get('E2EL_avg', ''),
                'E2EL_min': result.get('E2EL_min', ''),
                'E2EL_max': result.get('E2EL_max', ''),
                'E2EL_P90': result.get('E2EL P90', ''),
            }
            results.append(row)
            print(f"  ✓ 提取成功: input_len={row['input_len']}, output_len={row['output_len']}, "
                  f"TTFT_avg={row['TTFT_avg']}ms, TPOT_avg={row['TPOT_avg']}ms, "
                  f"external_hit_rate={row['external_hit_rate']}%")
        else:
            print(f"  ✗ 提取失败")
    
    if not results:
        print("\n未提取到任何有效数据")
        return
    
    # 写入CSV
    fieldnames = [
        'input_len', 'output_len', 'total_req', 'max_cc', 'cc',
        'hbm_hit_rate', 'external_hit_rate',
        'TTFT_avg', 'TTFT_min', 'TTFT_max', 'TTFT_P90',
        'TPOT_avg', 'TPOT_min', 'TPOT_max', 'TPOT_SLO_P90',
        'E2E_time',
        'output_throughput', 'E2E_throughput',
        'qps', 'qpm',
        'input_token_throughput', 'prefill_token_throughput',
        'E2EL_avg', 'E2EL_min', 'E2EL_max', 'E2EL_P90'
    ]
    
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\n✓ 结果已保存到: {output_csv}")
    print(f"  共 {len(results)} 条记录")
    
    print("\n预览:")
    print("-" * 100)
    for row in results:
        print(f"  input_len={row['input_len']}, output_len={row['output_len']}, "
              f"total_req={row['total_req']}, max_cc={row['max_cc']}, cc={row['cc']}, "
              f"TTFT_avg={row['TTFT_avg']}ms, TPOT_avg={row['TPOT_avg']}ms, "
              f"external_hit_rate={row['external_hit_rate']}%")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='从AISBench测试日志目录中提取第二次测试的性能指标',
        epilog='示例: python3 extract_metrics.py -d ./test_logs_20260911_200012 -o results.csv'
    )
    parser.add_argument('-d', '--dir', required=True, help='日志目录路径')
    parser.add_argument('-o', '--output', default='second_test_results.csv', help='输出CSV文件名')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.dir):
        print(f"错误: 目录不存在 - {args.dir}")
        return
    
    process_log_directory(args.dir, args.output)

if __name__ == "__main__":
    main()