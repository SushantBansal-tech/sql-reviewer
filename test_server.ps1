# test_server.ps1 - Complete server testing script

Write-Host "================================" -ForegroundColor Cyan
Write-Host "OpenEnv Server Testing Script" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

# Test 1: Health Check
Write-Host "[TEST 1] Health Check" -ForegroundColor Green
try {
    $response = Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✓ Server is running" -ForegroundColor Green
    Write-Host "Response: $($response.StatusCode) - $($content | ConvertTo-Json)`n"
} catch {
    Write-Host "✗ Server not responding" -ForegroundColor Red
    exit 1
}

# Test 2: Get Tasks
Write-Host "[TEST 2] Get All Tasks" -ForegroundColor Green
try {
    $response = Invoke-WebRequest http://localhost:8000/tasks -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✓ Found $($content.tasks.Count) tasks" -ForegroundColor Green
    foreach ($task in $content.tasks) {
        Write-Host "  - $($task.task_id) ($($task.difficulty))" -ForegroundColor Yellow
    }
    Write-Host ""
} catch {
    Write-Host "✗ Failed to get tasks" -ForegroundColor Red
    exit 1
}

# Test 3: Test Easy Task Grader (Correct Answer)
Write-Host "[TEST 3] Grade Easy Task (Correct SQL)" -ForegroundColor Green
$body = @{
    task_id = "easy_null_filter"
    fixed_query = "SELECT id, customer_id, total FROM orders WHERE status IS NULL ORDER BY created_at DESC;"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/grader" `
        -Method POST `
        -Headers @{"Content-Type"="application/json"} `
        -Body $body `
        -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✓ Task: $($content.task_id)" -ForegroundColor Green
    Write-Host "  Score: $($content.score)" -ForegroundColor Yellow
    Write-Host "  Feedback: $($content.feedback)" -ForegroundColor Yellow
    Write-Host "  Pass: $($content.pass)`n" -ForegroundColor Yellow
} catch {
    Write-Host "✗ Grader failed" -ForegroundColor Red
    exit 1
}

# Test 4: Test Easy Task Grader (Wrong Answer)
Write-Host "[TEST 4] Grade Easy Task (Wrong SQL - for comparison)" -ForegroundColor Green
$body = @{
    task_id = "easy_null_filter"
    fixed_query = "SELECT id, customer_id, total FROM orders WHERE status = NULL ORDER BY created_at DESC;"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/grader" `
        -Method POST `
        -Headers @{"Content-Type"="application/json"} `
        -Body $body `
        -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✓ Task: $($content.task_id)" -ForegroundColor Green
    Write-Host "  Score: $($content.score)" -ForegroundColor Yellow
    Write-Host "  Feedback: $($content.feedback)" -ForegroundColor Yellow
    Write-Host "  Pass: $($content.pass)`n" -ForegroundColor Yellow
} catch {
    Write-Host "✗ Grader failed" -ForegroundColor Red
    exit 1
}

# Test 5: Test Medium Task Grader
Write-Host "[TEST 5] Grade Medium Task (N+1 Problem)" -ForegroundColor Green
$body = @{
    task_id = "medium_n_plus_one"
    fixed_query = "SELECT oi.id, oi.order_id, oi.quantity, p.name, p.category FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.quantity > 5;"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/grader" `
        -Method POST `
        -Headers @{"Content-Type"="application/json"} `
        -Body $body `
        -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✓ Task: $($content.task_id)" -ForegroundColor Green
    Write-Host "  Score: $($content.score)" -ForegroundColor Yellow
    Write-Host "  Feedback: $($content.feedback)" -ForegroundColor Yellow
    Write-Host "  Pass: $($content.pass)`n" -ForegroundColor Yellow
} catch {
    Write-Host "✗ Grader failed" -ForegroundColor Red
    exit 1
}

# Test 6: Test Hard Task Grader
Write-Host "[TEST 6] Grade Hard Task (Complex Query)" -ForegroundColor Green
$body = @{
    task_id = "hard_multi_bug"
    fixed_query = "SELECT c.region, COUNT(DISTINCT c.id) as customer_count, SUM(o.total) as total_revenue FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.total > 100 GROUP BY c.region;"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/grader" `
        -Method POST `
        -Headers @{"Content-Type"="application/json"} `
        -Body $body `
        -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✓ Task: $($content.task_id)" -ForegroundColor Green
    Write-Host "  Score: $($content.score)" -ForegroundColor Yellow
    Write-Host "  Feedback: $($content.feedback)" -ForegroundColor Yellow
    Write-Host "  Pass: $($content.pass)`n" -ForegroundColor Yellow
} catch {
    Write-Host "✗ Grader failed" -ForegroundColor Red
    exit 1
}

Write-Host "================================" -ForegroundColor Cyan
Write-Host "✓ All tests passed!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Cyan