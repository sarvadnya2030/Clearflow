#!/usr/bin/env python3
"""Analyze 100K payment test results and log volume."""

import json
import subprocess
import sys
from datetime import datetime

def parse_test_output(log_file):
    """Parse batch_100k.py output."""
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        results = {
            'total_batches': 0,
            'total_sent': 0,
            'total_accepted': 0,
            'total_errors': 0,
            'acceptance_rate': 0.0,
            'error_rate': 0.0,
            'p99_latency': 0,
            'p95_latency': 0,
            'sla_pass': False,
            'batches': []
        }
        
        for line in lines:
            if 'Batch' in line and 'Sent:' in line:
                # Parse: Batch 1: Sent: 500, Accepted: 160, Errors: 177
                parts = line.split()
                try:
                    batch_num = int(parts[1].rstrip(':'))
                    sent = int(parts[4].rstrip(','))
                    accepted = int(parts[7].rstrip(','))
                    errors = int(parts[10])
                    
                    results['batches'].append({
                        'batch': batch_num,
                        'sent': sent,
                        'accepted': accepted,
                        'errors': errors
                    })
                    results['total_sent'] += sent
                    results['total_accepted'] += accepted
                    results['total_errors'] += errors
                except (ValueError, IndexError):
                    pass
            
            if 'Total' in line and 'Sent:' in line:
                parts = line.split()
                try:
                    results['total_sent'] = int(parts[3].rstrip(','))
                    results['total_accepted'] = int(parts[6].rstrip(','))
                    results['total_errors'] = int(parts[9])
                except (ValueError, IndexError):
                    pass
            
            if 'Acceptance Rate:' in line:
                try:
                    rate = float(line.split(':')[1].strip().rstrip('%')) / 100.0
                    results['acceptance_rate'] = rate
                except (ValueError, IndexError):
                    pass
            
            if 'Error Rate:' in line:
                try:
                    rate = float(line.split(':')[1].strip().rstrip('%')) / 100.0
                    results['error_rate'] = rate
                except (ValueError, IndexError):
                    pass
            
            if 'p99' in line and 'ms' in line:
                try:
                    val = int(line.split(':')[1].strip().split()[0])
                    results['p99_latency'] = val
                except (ValueError, IndexError):
                    pass
            
            if 'p95' in line and 'ms' in line:
                try:
                    val = int(line.split(':')[1].strip().split()[0])
                    results['p95_latency'] = val
                except (ValueError, IndexError):
                    pass
            
            if 'SLA' in line and ('PASS' in line or 'FAIL' in line):
                results['sla_pass'] = 'PASS' in line
        
        return results
    except FileNotFoundError:
        return None

def count_elasticsearch_logs():
    """Count logs in Elasticsearch clearflow-* indices."""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:9200/clearflow-*/_count"],
            capture_output=True,
            text=True,
            timeout=5
        )
        data = json.loads(result.stdout)
        return data.get('count', 0)
    except:
        return None

def print_report(test_results, log_count):
    """Print formatted test report."""
    print("\n" + "="*80)
    print("🎯 ClearFlow 100K PAYMENT TEST RESULTS")
    print("="*80)
    
    if not test_results:
        print("❌ Test output not found or not yet complete")
        return False
    
    print(f"\n📊 Payment Statistics")
    print(f"  Total Sent:      {test_results['total_sent']:,}")
    print(f"  Total Accepted:  {test_results['total_accepted']:,} ({test_results['acceptance_rate']:.2%})")
    print(f"  Total Errors:    {test_results['total_errors']:,} ({test_results['error_rate']:.2%})")
    
    print(f"\n⏱️  Latency")
    print(f"  p95: {test_results['p95_latency']}ms")
    print(f"  p99: {test_results['p99_latency']}ms")
    
    print(f"\n📈 Logs in Elasticsearch")
    if log_count:
        print(f"  Total Logs: {log_count:,}")
        expected = 700000
        percentage = (log_count / expected) * 100
        print(f"  Target: {expected:,}")
        print(f"  Achievement: {percentage:.1f}%")
        logs_ok = log_count >= (expected * 0.8)  # 80% of target
        print(f"  Status: {'✅ PASS' if logs_ok else '⚠️  BELOW TARGET'}")
    else:
        print(f"  Unable to query Elasticsearch")
    
    print(f"\n✅ SLA Status: {'PASS ✓' if test_results['sla_pass'] else 'FAIL ✗'}")
    
    # Batch breakdown
    if test_results['batches']:
        print(f"\n📋 Batch Details (first 5 + last 5)")
        for batch in test_results['batches'][:5]:
            rate = (batch['accepted'] / batch['sent']) * 100 if batch['sent'] > 0 else 0
            print(f"  Batch {batch['batch']:3d}: {batch['sent']:3d} sent, {batch['accepted']:3d} accepted ({rate:5.1f}%)")
        
        if len(test_results['batches']) > 10:
            print(f"  ... ({len(test_results['batches']) - 10} batches omitted)")
            for batch in test_results['batches'][-5:]:
                rate = (batch['accepted'] / batch['sent']) * 100 if batch['sent'] > 0 else 0
                print(f"  Batch {batch['batch']:3d}: {batch['sent']:3d} sent, {batch['accepted']:3d} accepted ({rate:5.1f}%)")
    
    print("\n" + "="*80)
    success = test_results['sla_pass'] and test_results['acceptance_rate'] > 0.95
    print(f"Overall Status: {'🎉 SUCCESS - Ready for Production!' if success else '⚠️  NEEDS INVESTIGATION'}")
    print("="*80 + "\n")
    
    return success

if __name__ == "__main__":
    log_file = "/tmp/test_100k_fixed.log"
    test_results = parse_test_output(log_file)
    log_count = count_elasticsearch_logs()
    
    success = print_report(test_results, log_count)
    sys.exit(0 if success else 1)
