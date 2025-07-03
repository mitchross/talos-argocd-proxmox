# ArgoCD ApplicationSet Template Resolution Fix

## 🚨 Current Issue
**Error**: `{{.path}}: app path does not exist`  
**Root Cause**: ArgoCD ApplicationSet controller is not resolving template variables properly

## 🔧 Step-by-Step Solutions

### **Solution 1: Test Manual Application (Immediate)**

1. **Enable the manual cloudnative-pg application**:
   ```bash
   # Edit the kustomization.yaml
   sed -i 's/# - manual-cloudnative-pg-app.yaml/  - manual-cloudnative-pg-app.yaml/' infrastructure/controllers/argocd/apps/kustomization.yaml
   
   # Commit and push
   git add infrastructure/controllers/argocd/apps/
   git commit -m "test: enable manual cloudnative-pg application"
   git push origin main
   ```

2. **Verify**: Check if `manual-cloudnative-pg` application syncs successfully in ArgoCD UI

### **Solution 2: Use Explicit ApplicationSet (Recommended)**

If the manual application works, replace the directory-discovery ApplicationSet:

1. **Switch to explicit ApplicationSet**:
   ```bash
   # Comment out the problematic ApplicationSet and enable the explicit one
   sed -i 's/  - appsets\/infrastructure-appset.yaml/  # - appsets\/infrastructure-appset.yaml/' infrastructure/controllers/argocd/apps/kustomization.yaml
   sed -i 's/# - appsets\/infrastructure-explicit.yaml/  - appsets\/infrastructure-explicit.yaml/' infrastructure/controllers/argocd/apps/kustomization.yaml
   
   # Commit and push
   git add infrastructure/controllers/argocd/apps/kustomization.yaml
   git commit -m "fix: switch to explicit ApplicationSet for infrastructure"
   git push origin main
   ```

### **Solution 3: Fix Template Variables**

If you prefer to keep directory discovery:

1. **Try the fixed template version**:
   ```bash
   # Enable the fixed ApplicationSet (uses {{path}} instead of {{.path}})
   sed -i 's/# - appsets\/infrastructure-appset-fixed.yaml/  - appsets\/infrastructure-appset-fixed.yaml/' infrastructure/controllers/argocd/apps/kustomization.yaml
   
   git add infrastructure/controllers/argocd/apps/kustomization.yaml
   git commit -m "test: try fixed template variables in ApplicationSet"
   git push origin main
   ```

### **Solution 4: Nuclear Option - Restart ArgoCD Components**

If template resolution is completely broken:

```bash
# Restart ApplicationSet controller
kubectl rollout restart deployment/argocd-applicationset-controller -n argocd

# Restart ArgoCD server
kubectl rollout restart deployment/argocd-server -n argocd

# Clear all repository caches
kubectl exec -n argocd deployment/argocd-repo-server -- find /tmp -name "*github.com*" -exec rm -rf {} +
```

## 🔍 What I Created for You

### **1. Manual Application** (`manual-cloudnative-pg-app.yaml`)
- Direct Application resource for cloudnative-pg
- Bypasses ApplicationSet completely
- Tests if the path `infrastructure/database/cloudnative-pg` works

### **2. Fixed ApplicationSet** (`infrastructure-appset-fixed.yaml`)
- Uses `{{path}}` instead of `{{.path}}`
- Adds retry policies and debugging annotations
- More robust error handling

### **3. Explicit ApplicationSet** (`infrastructure-explicit.yaml`)
- Lists each application explicitly
- No directory discovery - zero ambiguity
- **Most reliable approach**

## 📋 Key Differences in Template Variables

| Version | Template Variable | Generator Type |
|---------|------------------|----------------|
| Original | `{{.path}}` | git directories |
| Fixed | `{{path}}` | git directories |  
| Explicit | `{{path}}` | list |

## ✅ Testing Order

1. **First**: Test manual application → proves path works
2. **Second**: Test explicit ApplicationSet → proves template resolution works
3. **Third**: Fall back to directory discovery if needed

## 🚀 Expected Results

- **Manual app works**: Path is valid, issue is with ApplicationSet template resolution
- **Explicit ApplicationSet works**: Template variables work, issue is with directory discovery
- **Both fail**: Deeper ArgoCD or repository access issue

## 🔧 Rollback Plan

If anything breaks:
```bash
# Restore original configuration
git checkout HEAD~1 infrastructure/controllers/argocd/apps/kustomization.yaml
git commit -m "rollback: restore original ApplicationSet configuration"
git push origin main
```

Choose **Solution 2 (Explicit ApplicationSet)** for the most reliable long-term fix!