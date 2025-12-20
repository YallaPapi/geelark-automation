"""
Flow Log Analyzer - Phase 3 of Hybrid Posting System

Parses all JSONL flow logs, aggregates screen signatures,
and identifies common screens for deterministic rule creation.
"""
import os
import json
import glob
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any


def parse_flow_logs(log_dir: str = "flow_analysis") -> List[Dict]:
    """Parse all JSONL flow logs from directory.

    Args:
        log_dir: Directory containing JSONL flow logs.

    Returns:
        List of all log entries across all files.
    """
    all_entries = []
    log_files = glob.glob(os.path.join(log_dir, "*.jsonl"))

    print(f"Found {len(log_files)} log files in {log_dir}/")

    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry['_source_file'] = os.path.basename(log_file)
                        all_entries.append(entry)
                    except json.JSONDecodeError as e:
                        pass  # Skip malformed lines
        except Exception as e:
            print(f"  Error reading {log_file}: {e}")

    return all_entries


def analyze_screen_signatures(entries: List[Dict]) -> Dict[str, Dict]:
    """Analyze screen signatures and their frequencies.

    Args:
        entries: List of all log entries.

    Returns:
        Dict mapping signature -> analysis data.
    """
    # Group step entries by screen signature
    signature_data = defaultdict(lambda: {
        'count': 0,
        'sample_elements': None,
        'actions_taken': Counter(),
        'next_signatures': Counter(),
        'ai_called_count': 0,
        'source_accounts': set(),
        'step_positions': []  # Which step number this appears at
    })

    # Process step events
    step_entries = [e for e in entries if e.get('event') == 'step']
    print(f"Processing {len(step_entries)} step entries...")

    for i, entry in enumerate(step_entries):
        sig = entry.get('screen_signature')
        if not sig:
            continue

        data = signature_data[sig]
        data['count'] += 1

        # Store sample elements (first occurrence)
        if data['sample_elements'] is None:
            data['sample_elements'] = entry.get('elements_summary', [])

        # Track actions taken on this screen
        action = entry.get('action', {})
        action_type = action.get('action', 'unknown')
        data['actions_taken'][action_type] += 1

        # Track if AI was called
        if entry.get('ai_called'):
            data['ai_called_count'] += 1

        # Track source accounts
        source_file = entry.get('_source_file', '')
        account = source_file.split('_')[0] if source_file else 'unknown'
        data['source_accounts'].add(account)

        # Track step position
        data['step_positions'].append(entry.get('step', 0))

        # Track next signature (for transition mapping)
        if i + 1 < len(step_entries):
            next_entry = step_entries[i + 1]
            # Only count if same session (same source file)
            if next_entry.get('_source_file') == entry.get('_source_file'):
                next_sig = next_entry.get('screen_signature')
                if next_sig:
                    data['next_signatures'][next_sig] += 1

    return dict(signature_data)


def analyze_successful_flows(entries: List[Dict]) -> Dict:
    """Analyze patterns from successful posting flows only.

    Args:
        entries: List of all log entries.

    Returns:
        Analysis of successful flows.
    """
    # Group entries by source file
    sessions = defaultdict(list)
    for entry in entries:
        source = entry.get('_source_file', 'unknown')
        sessions[source].append(entry)

    successful_sessions = []
    failed_sessions = []

    for source, session_entries in sessions.items():
        has_success = any(e.get('event') == 'success' for e in session_entries)
        has_failure = any(e.get('event') == 'failure' for e in session_entries)

        if has_success:
            successful_sessions.append((source, session_entries))
        elif has_failure:
            failed_sessions.append((source, session_entries))

    print(f"Found {len(successful_sessions)} successful sessions, {len(failed_sessions)} failed sessions")

    # Analyze successful flow patterns
    successful_flows = []
    for source, session_entries in successful_sessions:
        steps = [e for e in session_entries if e.get('event') == 'step']
        flow = [s.get('screen_signature') for s in steps]
        successful_flows.append({
            'source': source,
            'flow': flow,
            'step_count': len(steps)
        })

    # Find common flow patterns
    flow_patterns = Counter()
    for f in successful_flows:
        # Create a pattern key from the flow
        pattern = tuple(f['flow'])
        flow_patterns[pattern] += 1

    return {
        'successful_count': len(successful_sessions),
        'failed_count': len(failed_sessions),
        'successful_flows': successful_flows,
        'common_patterns': flow_patterns.most_common(10)
    }


def identify_screen_types(signature_data: Dict[str, Dict]) -> Dict[str, str]:
    """Attempt to identify screen types from element patterns.

    Args:
        signature_data: Screen signature analysis data.

    Returns:
        Dict mapping signature -> guessed screen type.
    """
    screen_types = {}

    for sig, data in signature_data.items():
        elements = data.get('sample_elements', [])
        if not elements:
            screen_types[sig] = 'UNKNOWN'
            continue

        # Extract text and descriptions
        texts = [e.get('text', '').lower() for e in elements]
        descs = [e.get('desc', '').lower() for e in elements]
        all_text = ' '.join(texts + descs)

        # Heuristic detection - order matters (most specific first)

        # Verification/ID popups
        if 'upload your id' in all_text or 'verify your identity' in all_text:
            screen_types[sig] = 'POPUP_VERIFICATION'

        # Login/logged out
        elif 'log in' in all_text or 'sign in' in all_text or 'create new account' in all_text:
            screen_types[sig] = 'LOGIN_SCREEN'

        # Share preview screen (has caption input AND edit cover)
        elif 'write a caption' in all_text or ('edit cover' in all_text and 'caption' in all_text):
            screen_types[sig] = 'SHARE_PREVIEW'

        # Video editing screen (has Next button AND edit video)
        elif ('edit video' in all_text or 'swipe up to edit' in all_text) and 'next' in all_text:
            screen_types[sig] = 'VIDEO_EDITING'

        # Gallery picker (New reel title)
        elif 'new reel' in all_text:
            screen_types[sig] = 'GALLERY_PICKER'

        # Sharing in progress
        elif 'sharing' in all_text or 'posting' in all_text or 'uploading' in all_text:
            screen_types[sig] = 'SHARING_PROGRESS'

        # Create menu (Reel + Story options visible)
        elif 'reel' in texts and ('story' in texts or 'post' in texts):
            screen_types[sig] = 'CREATE_MENU'

        # Profile screen
        elif any('profile' in t for t in texts + descs) or ('posts' in all_text and 'followers' in all_text):
            screen_types[sig] = 'PROFILE_SCREEN'

        # Feed/Home screen
        elif any('home' in d for d in descs) or 'reels tray' in all_text or "story" in all_text and 'unseen' in all_text:
            screen_types[sig] = 'FEED_SCREEN'

        # Dismissible popups
        elif 'not now' in all_text or 'dismiss' in all_text or 'skip' in all_text or 'later' in all_text:
            screen_types[sig] = 'POPUP_DISMISSIBLE'

        # Success confirmation
        elif 'shared' in all_text or 'your reel is' in all_text:
            screen_types[sig] = 'SUCCESS_SCREEN'

        else:
            screen_types[sig] = 'UNKNOWN'

    return screen_types


def generate_report(signature_data: Dict, screen_types: Dict, flow_analysis: Dict,
                   output_file: str = "screen_analysis_report.json"):
    """Generate comprehensive analysis report.

    Args:
        signature_data: Screen signature analysis.
        screen_types: Identified screen types.
        flow_analysis: Successful flow analysis.
        output_file: Output file path.
    """
    # Sort signatures by frequency
    sorted_sigs = sorted(signature_data.items(), key=lambda x: x[1]['count'], reverse=True)

    report = {
        'summary': {
            'total_signatures': len(signature_data),
            'total_step_entries': sum(d['count'] for d in signature_data.values()),
            'successful_sessions': flow_analysis['successful_count'],
            'failed_sessions': flow_analysis['failed_count'],
            'screen_type_distribution': Counter(screen_types.values())
        },
        'top_signatures': [],
        'screen_type_mapping': screen_types,
        'successful_flow_samples': flow_analysis['successful_flows'][:10]
    }

    # Top 50 signatures with details
    for sig, data in sorted_sigs[:50]:
        avg_step = sum(data['step_positions']) / len(data['step_positions']) if data['step_positions'] else 0

        report['top_signatures'].append({
            'signature': sig,
            'count': data['count'],
            'screen_type': screen_types.get(sig, 'UNKNOWN'),
            'ai_called_count': data['ai_called_count'],
            'ai_call_rate': data['ai_called_count'] / data['count'] if data['count'] > 0 else 0,
            'avg_step_position': round(avg_step, 1),
            'unique_accounts': len(data['source_accounts']),
            'top_actions': data['actions_taken'].most_common(3),
            'top_next_screens': data['next_signatures'].most_common(3),
            'sample_elements': data['sample_elements'][:10] if data['sample_elements'] else []
        })

    # Write report
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nReport written to {output_file}")
    return report


def print_summary(report: Dict):
    """Print human-readable summary to console."""
    print("\n" + "="*60)
    print("SCREEN SIGNATURE ANALYSIS SUMMARY")
    print("="*60)

    summary = report['summary']
    print(f"\nTotal unique screen signatures: {summary['total_signatures']}")
    print(f"Total step entries analyzed: {summary['total_step_entries']}")
    print(f"Successful sessions: {summary['successful_sessions']}")
    print(f"Failed sessions: {summary['failed_sessions']}")

    print(f"\nScreen Type Distribution:")
    for screen_type, count in sorted(summary['screen_type_distribution'].items(), key=lambda x: -x[1]):
        print(f"  {screen_type}: {count}")

    print(f"\nTop 20 Most Common Screens:")
    print("-"*60)
    for i, sig_data in enumerate(report['top_signatures'][:20], 1):
        ai_rate = sig_data['ai_call_rate'] * 100
        print(f"{i:2}. [{sig_data['screen_type']:20}] sig={sig_data['signature']} "
              f"count={sig_data['count']:4} AI={ai_rate:5.1f}% step~{sig_data['avg_step_position']:.0f}")

        # Show sample text
        if sig_data['sample_elements']:
            texts = [e.get('text', '') for e in sig_data['sample_elements'][:5] if e.get('text')]
            if texts:
                print(f"     Elements: {texts[:3]}")


def main():
    """Main analysis entry point."""
    print("Flow Log Analyzer - Phase 3")
    print("="*60)

    # Parse all logs
    entries = parse_flow_logs("flow_analysis")
    print(f"Total entries parsed: {len(entries)}")

    if not entries:
        print("No entries found. Make sure flow_analysis/ contains JSONL files.")
        return

    # Analyze screen signatures
    print("\nAnalyzing screen signatures...")
    signature_data = analyze_screen_signatures(entries)
    print(f"Found {len(signature_data)} unique screen signatures")

    # Identify screen types
    print("\nIdentifying screen types...")
    screen_types = identify_screen_types(signature_data)

    # Analyze successful flows
    print("\nAnalyzing successful flows...")
    flow_analysis = analyze_successful_flows(entries)

    # Generate report
    report = generate_report(signature_data, screen_types, flow_analysis)

    # Print summary
    print_summary(report)

    print("\n" + "="*60)
    print("Analysis complete!")
    print("="*60)


if __name__ == "__main__":
    main()
