@echo off
echo [1/3] Adding changes to Git...
git add .
echo [2/3] Committing changes...
git commit -m "Implement GraphRAG 0.4: Upgrade PHP AST parsing, archive legacy REST API, and expose python module interface"
echo [3/3] Pushing to remote...
git push
echo ==============================================
echo ✅ Changes successfully pushed to repository!
echo ==============================================
pause
