# Hybrid System Restoration PRD

## Executive Summary

The hybrid posting system achieved 98% effectiveness with 120+ successful posts before breaking. The follow system works at 92% effectiveness using AI-only. This PRD outlines the plan to:
1. Restore hybrid posting to 98% effectiveness
2. Convert follow system to hybrid (currently AI-only at 92%, target 95%+ as hybrid)
3. Create a systematized hybrid development process for future modules
4. Document everything to prevent future issues

## Problem Statement

### Current State
- **Hybrid posting**: Broken - gets stuck on screens, taps wrong elements
- **Follow system**: Working at 92% - uses AI-driven approach with rule shortcuts
- **Logging system**: Truncated (20 elements, 50 chars) - insufficient for debugging
- **12/17 flow logs**: Complete data exists but created by code no longer in codebase
- **Documentation**: Scattered, incomplete

### Root Causes Identified
1. **Screen detection rules incorrect**: `screen_detector.py` patterns don't match current Instagram screens
2. **Action mappings wrong**: `action_engine.py` returns wrong tap targets or coordinates
3. **Logging truncation**: `FlowLogger` truncates data, making debugging impossible
4. **No systematic development process**: Hybrid rules were built ad-hoc without reproducible methodology

## Goals

### Primary Goals
1. Restore hybrid posting to 98%+ success rate
2. Convert follow system to hybrid at 95%+ success rate (currently AI-only at 92%)
3. Create reusable hybrid development system for future modules

### Secondary Goals
1. Complete documentation of hybrid development process
2. Clean up codebase (remove clutter, organize files)
3. Enable future modules: commenting, story posting, etc.

## Technical Approach

### Phase 1: Environment Setup
**Objective**: Get to a clean starting point with working follow system

1. Checkout follow commit (fdd41f6) as new branch `hybrid-restoration`
2. Verify follow system still works (run 5 test follows)
3. Document current state of all systems

### Phase 2: Fix Logging Infrastructure
**Objective**: Enable complete data capture for debugging and analysis

1. Update `FlowLogger` to remove ALL truncation limits:
   - `max_elements`: Remove limit entirely (log all elements)
   - Text truncation: Remove entirely (log full text/desc)
   - Match the format of 12/17 logs which have complete `ui_elements` arrays
2. Add optional screenshot capture at each step
3. Add before/after tap verification logging
4. Test logging with manual run

### Phase 3: Restore AI-Only Posting
**Objective**: Get posting working immediately while we fix hybrid

**Reference**: Commit 05de639 contains working AI-only posting (98% success rate)
- Uses `self.analyze_ui(elements, caption)` instead of `navigator.navigate(elements)`
- No HybridNavigator, ScreenDetector, or ActionEngine dependencies

1. Restore AI-only posting from commit 05de639:
   - Either checkout `post_reel_smart.py` from 05de639
   - Or modify current version to bypass HybridNavigator and use `analyze_ui()` directly
2. Add FlowLogger integration (with no truncation) to capture complete data during AI-only runs
3. Test AI-only posting on 5 accounts
4. Verify 95%+ success rate matches original 98%

### Phase 4: Collect Fresh Flow Data
**Objective**: Gather complete, accurate data for rebuilding hybrid rules

1. Run full AI-only posting campaign on BOTH podcast + viral campaigns with full logging
2. Ensure logs capture ALL elements (no truncation)
3. Separate successful flows from failed flows
4. Target: Maximum successful flow logs from full campaign run

### Phase 5: Analyze and Map Screens
**Objective**: Build accurate screen detection rules from real data

1. Create `analyze_flows.py` - improved analysis script
2. Identify all unique screen types from successful flows
3. For each screen, document:
   - Key identifying elements (text, desc patterns)
   - Required action (what to tap/type)
   - Expected next screen
4. Generate screen detection rules automatically where possible

### Phase 6: Rebuild Hybrid Components
**Objective**: Create correct, tested hybrid rules

1. Rebuild `screen_detector.py` from fresh analysis
2. Rebuild `action_engine.py` with correct tap targets
3. Update `hybrid_navigator.py` if needed
4. Unit test each component with real screen data

### Phase 7: Integration Testing
**Objective**: Validate hybrid system works end-to-end

1. Run hybrid posting on 10 accounts
2. Compare success rate to AI-only baseline
3. Debug any failures using complete logs
4. Iterate until 95%+ success rate achieved

### Phase 8: Documentation and Cleanup
**Objective**: Prevent future issues, enable future development

1. Document hybrid development process in `docs/HYBRID_DEVELOPMENT.md`
2. Document each screen type and its detection rules
3. Create template for adding new modules
4. Clean up:
   - Remove obsolete files
   - Archive old logs
   - Organize folder structure
5. Update CLAUDE.md with new processes

---

## Follow System Hybrid Conversion (After Posting Hybrid Complete)

### Phase 9: Collect Follow Flow Data
**Objective**: Gather complete data for follow hybrid rules

1. Add FlowLogger to follow_single.py (with no truncation)
2. Run full AI-only follow campaign on BOTH podcast + viral campaigns with full logging
3. Target: Maximum successful follow flow logs from full campaign run
4. Document follow-specific screens (search, explore, profile, etc.)

### Phase 10: Build Follow Hybrid Components
**Objective**: Create hybrid rules for follow system

1. Analyze follow flow logs to identify screen types
2. Add follow screen types to `screen_detector.py`:
   - EXPLORE_PAGE, SEARCH_INPUT, SEARCH_RESULTS, TARGET_PROFILE, etc.
3. Add follow action handlers to `action_engine.py`
4. Create `follow_hybrid_navigator.py` or extend existing hybrid navigator
5. Unit test follow hybrid components

### Phase 11: Follow Hybrid Testing
**Objective**: Validate follow hybrid works at 95%+

1. Run hybrid follows on 10 accounts
2. Compare success rate to AI-only baseline (92%)
3. Debug failures using complete logs
4. Iterate until 95%+ success rate achieved

---

## File Changes

### Key Commits Reference
| Commit | Description | Restore From |
|--------|-------------|--------------|
| 05de639 | AI-only posting (98% success) | `post_reel_smart.py` |
| fdd41f6 | Working follow system (92%) | `follow_single.py`, `follow_worker.py`, `follow_orchestrator.py` |
| 9492f96 | Hybrid system (broken) | Reference only - rebuild components |

### New Files
- `.taskmaster/docs/hybrid_system_restoration_prd.md` (this file)
- `analyze_flows.py` - Improved flow analysis script
- `docs/HYBRID_DEVELOPMENT.md` - Development process documentation
- `docs/SCREEN_TYPES.md` - Screen detection reference

### Modified Files
- `flow_logger.py` - Remove truncation limits
- `screen_detector.py` - Rebuilt with correct rules
- `action_engine.py` - Rebuilt with correct mappings
- `hybrid_navigator.py` - Updates if needed
- `CLAUDE.md` - Add hybrid development section

### Files to Archive/Remove
- Old flow logs (archive to `archived/flow_analysis_YYYYMMDD/`)
- Duplicate progress CSV files
- Test scripts no longer needed

## Success Criteria

### Phase 1-3 (Week 1)
- [ ] Follow system verified working at 92%+
- [ ] FlowLogger captures complete data (verified manually)
- [ ] AI-only posting works at 95%+

### Phase 4-6 (Week 2)
- [ ] Full podcast + viral campaign posting runs completed with logging
- [ ] All screen types documented with detection rules
- [ ] Hybrid components rebuilt and unit tested

### Phase 7-8 (Week 3)
- [ ] Hybrid posting at 95%+ success rate
- [ ] Documentation complete
- [ ] Codebase cleaned up

### Phase 9-11 (Week 4)
- [ ] Full podcast + viral campaign follow runs completed with logging
- [ ] Follow hybrid components built and tested
- [ ] Follow hybrid at 95%+ success rate

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Instagram UI changes during development | High | Use AI-only as fallback, update rules as needed |
| Account bans during testing | Medium | Use test accounts, spread across accounts |
| Flow logs still incomplete | Medium | Add screenshot capture as backup |
| Hybrid never matches AI-only performance | Low | Keep AI-only as production option, hybrid for cost savings |

## Dependencies

- Working Geelark accounts (need 20+ for testing)
- Appium server functional
- Claude API access
- Git branches properly managed

## Future Modules (After Restoration)

Once hybrid development system is working:
1. **Commenting module** - Auto-comment on posts
2. **Story posting module** - Post to Instagram Stories
3. **DM module** - Send direct messages
4. **Engagement module** - Like/save posts

Each can follow the documented hybrid development process.

## Appendix: Current Branch State

| Branch | Posting | Follow | Notes |
|--------|---------|--------|-------|
| master (9492f96) | Hybrid (broken) | None | Current HEAD |
| fdd41f6 | Hybrid (broken) | AI-driven (92%) | Has working follow |
| c39b33a | Hybrid (broken) | AI-driven (works) | Failed fix attempts |

## Appendix: Key Files Reference

| File | Purpose | Status |
|------|---------|--------|
| `flow_logger.py` | Step logging | Needs fix (truncation) |
| `screen_detector.py` | Screen identification | Needs rebuild |
| `action_engine.py` | Action determination | Needs rebuild |
| `hybrid_navigator.py` | Orchestrates hybrid flow | May need updates |
| `analyze_logs.py` | Log analysis | Needs improvement |
| `follow_single.py` | Follow automation | Working (reference) |
| `post_reel_smart.py` | Posting automation | Uses broken hybrid |
