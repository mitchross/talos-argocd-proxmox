import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Copy } from 'lucide-react';

const ManifestGenerator = () => {
  const [formData, setFormData] = useState({
    appName: '',
    image: '',
    imageTag: 'latest',
    domainName: '',
    port: '8080',
    needsStorage: false,
    storageClassName: '',
    pvcName: '',
    storageSize: '1Gi'
  });

  const [generatedYaml, setGeneratedYaml] = useState('');
  const [copied, setCopied] = useState(false);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleStorageChange = (checked) => {
    setFormData(prev => ({
      ...prev,
      needsStorage: checked
    }));
  };

  const generateYaml = () => {
    const deployment = `apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${formData.appName}
  namespace: ${formData.appName}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${formData.appName}
  template:
    metadata:
      labels:
        app: ${formData.appName}
    spec:
      containers:
      - name: ${formData.appName}
        image: ${formData.image}:${formData.imageTag}
        ports:
        - containerPort: ${formData.port}
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"${formData.needsStorage ? `
        volumeMounts:
        - name: data
          mountPath: /data` : ''}
---
apiVersion: v1
kind: Service
metadata:
  name: ${formData.appName}
  namespace: ${formData.appName}
spec:
  ports:
  - port: ${formData.port}
    targetPort: ${formData.port}
  selector:
    app: ${formData.appName}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${formData.pvcName}
  namespace: ${formData.appName}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${formData.storageSize}
  storageClassName: ${formData.storageClassName}`;

    setGeneratedYaml(deployment);
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(generatedYaml);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div className="container mx-auto p-4 max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>Kubernetes Manifest Generator</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <Label htmlFor="appName">Application Name</Label>
              <Input
                id="appName"
                name="appName"
                value={formData.appName}
                onChange={handleInputChange}
                placeholder="my-app"
              />
            </div>
            <div>
              <Label htmlFor="image">Docker Image</Label>
              <Input
                id="image"
                name="image"
                value={formData.image}
                onChange={handleInputChange}
                placeholder="nginx"
              />
            </div>
            <div>
              <Label htmlFor="imageTag">Image Tag</Label>
              <Input
                id="imageTag"
                name="imageTag"
                value={formData.imageTag}
                onChange={handleInputChange}
                placeholder="latest"
              />
            </div>
            <div>
              <Label htmlFor="domainName">Domain Name</Label>
              <Input
                id="domainName"
                name="domainName"
                value={formData.domainName}
                onChange={handleInputChange}
                placeholder="app.example.com"
              />
            </div>
            <div>
              <Label htmlFor="port">Port</Label>
              <Input
                id="port"
                name="port"
                type="number"
                value={formData.port}
                onChange={handleInputChange}
                placeholder="8080"
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="needsStorage"
                checked={formData.needsStorage}
                onCheckedChange={handleStorageChange}
              />
              <Label htmlFor="needsStorage">Needs Storage</Label>
            </div>
            {formData.needsStorage && (
              <div className="space-y-4">
                <div>
                  <Label htmlFor="storageClassName">Storage Class Name</Label>
                  <Input
                    id="storageClassName"
                    name="storageClassName"
                    value={formData.storageClassName}
                    onChange={handleInputChange}
                    placeholder="standard"
                  />
                </div>
                <div>
                  <Label htmlFor="pvcName">PVC Name</Label>
                  <Input
                    id="pvcName"
                    name="pvcName"
                    value={formData.pvcName}
                    onChange={handleInputChange}
                    placeholder="my-app-data"
                  />
                </div>
                <div>
                  <Label htmlFor="storageSize">Storage Size</Label>
                  <Input
                    id="storageSize"
                    name="storageSize"
                    value={formData.storageSize}
                    onChange={handleInputChange}
                    placeholder="1Gi"
                  />
                </div>
              </div>
            )}
            <Button onClick={generateYaml} className="w-full">Generate YAML</Button>
          </div>
          {generatedYaml && (
            <div className="mt-4">
              <div className="flex justify-between items-center mb-2">
                <Label>Generated YAML</Label>
                <Button variant="outline" size="sm" onClick={copyToClipboard}>
                  <Copy className="h-4 w-4 mr-2" />
                  Copy
                </Button>
              </div>
              <pre className="bg-slate-950 text-slate-50 p-4 rounded-lg overflow-x-auto">
                {generatedYaml}
              </pre>
              {copied && (
                <Alert className="mt-2">
                  <AlertDescription>
                    Copied to clipboard!
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ManifestGenerator;
