#!/bin/bash

echo "🧹 Starting cleanup process..."

# Clean analysis_agent folder completely
echo "  → Cleaning analysis_agent folder..."
rm -rf analysis_agent/*

# Clean visualization_agent folder completely  
echo "  → Cleaning visualization_agent folder..."
rm -rf visualization_agent/*

# Clean preparation_agent folder but keep input_dataset.csv
echo "  → Cleaning preparation_agent folder (keeping input_dataset.csv)..."
find preparation_agent -type f ! -name "input_dataset.csv" -delete
find preparation_agent -type d -mindepth 1 -delete

# Empty shared_knowledge.xml file
echo "  → Emptying shared_knowledge.xml..."
> shared_knowledge.xml

echo "✅ Cleanup completed successfully!"
echo ""
echo "Summary:"
echo "  - analysis_agent/: All files removed"
echo "  - visualization_agent/: All files removed" 
echo "  - preparation_agent/: All files removed except input_dataset.csv"
echo "  - shared_knowledge.xml: Emptied" 