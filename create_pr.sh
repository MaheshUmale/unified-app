#!/bin/bash

# Script to create a PR for the Enhanced Options Trading Features

echo "=========================================="
echo "ProTrade Enhanced Options Trading - PR Creator"
echo "=========================================="
echo ""

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "Error: Not a git repository. Please run this from the repository root."
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "Warning: You have uncommitted changes."
    read -p "Do you want to stash them? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git stash
        echo "Changes stashed."
    fi
fi

# Create a new branch
BRANCH_NAME="feature/enhanced-options-trading-$(date +%Y%m%d)"
echo "Creating branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

# Add new files
echo "Adding new files..."
git add backend/core/greeks_calculator.py
git add backend/core/iv_analyzer.py
git add backend/core/oi_buildup_analyzer.py
git add backend/core/strategy_builder.py
git add backend/core/alert_system.py
git add backend/core/options_manager.py
git add backend/core/__init__.py
git add backend/api_server.py
git add backend/config.py
git add backend/templates/options_dashboard.html
git add OPTIONS_ENHANCEMENTS.md
git add PR_DESCRIPTION.md

# Show status
echo ""
echo "Git status:"
git status

# Commit
echo ""
echo "Committing changes..."
git commit -m "feat: Enhanced Options Trading Platform with Greeks, IV Analysis, and Strategy Builder

This commit introduces comprehensive enhancements to the NSE Options Trading App:

New Modules:
- Greeks Calculator: Real-time Delta, Gamma, Theta, Vega, Rho calculation
- IV Analyzer: IV Rank, Percentile, Skew, and Term Structure analysis
- OI Buildup Analyzer: Long/Short Buildup detection and sentiment analysis
- Strategy Builder: Multi-leg strategy creation with P&L visualization
- Alert System: Price, OI, PCR, and IV threshold alerts

Enhanced Features:
- Options chain with real-time Greeks display
- Support/Resistance levels based on OI concentration
- PCR trend analysis with historical charts
- Strategy recommendations based on market view and IV
- Interactive dashboard with tabbed interface

API Endpoints Added:
- 15+ new endpoints for options analysis
- Strategy builder endpoints
- Alert management endpoints

Documentation:
- OPTIONS_ENHANCEMENTS.md with feature details
- PR_DESCRIPTION.md with comprehensive PR info

Closes: #enhancement-options-trading"

# Push branch
echo ""
read -p "Push branch to origin? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push -u origin "$BRANCH_NAME"
    echo ""
    echo "Branch pushed to origin/$BRANCH_NAME"
    echo ""
    echo "Next steps:"
    echo "1. Go to GitHub: https://github.com/MaheshUmale/unified-app"
    echo "2. Click 'Compare & pull request'"
    echo "3. Use PR_DESCRIPTION.md as the PR description"
    echo "4. Request reviews"
fi

echo ""
echo "=========================================="
echo "PR Branch: $BRANCH_NAME"
echo "=========================================="
