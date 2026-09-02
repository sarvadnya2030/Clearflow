"""Human-in-the-Loop CLI interface for agent recommendations."""

from repair_agent import RepairSuggestion

class HumanInTheLoopCLI:
    """CLI interface for operator to approve/reject agent repair suggestions."""
    
    def present_suggestion(self, suggestion: RepairSuggestion) -> dict:
        """Display a suggestion and get operator decision."""
        print("\n" + "="*70)
        print("⚙️  DIAGNOSTIC AGENT RECOMMENDATION")
        print("="*70)
        print(f"Failure Type:        {suggestion.failure_type}")
        print(f"Root Cause:          {suggestion.root_cause}")
        print(f"Confidence:          {suggestion.confidence:.0%}")
        print(f"\nProposed Fix:        {suggestion.fix_description}")
        if suggestion.impact:
            print(f"Impact:              {suggestion.impact}")
        print(f"Auto-Safe:           {'Yes ✓' if suggestion.auto_safe else 'No ✗ (requires approval)'}")
        
        if suggestion.fix_command:
            print(f"\nCommand:             {suggestion.fix_command}")
        if suggestion.config_file:
            print(f"Config File:         {suggestion.config_file}")
            if suggestion.config_change:
                print(f"Change:              {suggestion.config_change}")
        
        print("\nOptions:")
        print("  [A]pprove and execute")
        print("  [R]eject and explain why")
        print("  [S]kip this alert")
        
        while True:
            choice = input("\nYour decision [A/R/S]: ").strip().upper()
            if choice in ['A', 'R', 'S']:
                break
            print("Invalid choice. Enter A, R, or S.")
        
        if choice == 'A':
            return {"approved": True, "modified": False}
        elif choice == 'R':
            reason = input("Rejection reason (for learning): ")
            return {"approved": False, "reason": reason}
        else:
            return {"approved": False, "skipped": True}
