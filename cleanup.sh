#!/bin/bash
echo "🧹 Starting cleanup process..."

# Clean analysis_agent folder completely
echo "  → Cleaning analysis_agent folder..."
rm -rf analysis_agent/*

# Clean report_agent folder completely  
echo "  → Cleaning report_agent folder..."
rm -rf report_agent/*

# Clean preparation_agent folder but keep input_dataset.csv
echo "  → Cleaning preparation_agent folder (keeping input_dataset.csv)..."
find preparation_agent -type f ! -name "input_dataset.csv" -delete
find preparation_agent -type d -mindepth 1 -delete

# Remove __pycache__ folders
echo "  → Removing __pycache__ folders..."
find . -type d -name "__pycache__" -exec rm -rf {} +

# Empty shared_knowledge.xml file
echo "  → Emptying shared_knowledge.xml..."
> shared_knowledge.xml

echo "✅ Cleanup completed successfully!"
echo ""
echo "Summary:"
echo "  - analysis_agent/: All files removed"
echo "  - report_agent/: All files removed" 
echo "  - preparation_agent/: All files removed except input_dataset.csv"
echo "  - __pycache__/: All cache folders removed"
echo "  - shared_knowledge.xml: Emptied"