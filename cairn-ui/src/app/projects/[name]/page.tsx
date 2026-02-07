"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface ProjectDetail {
  name: string;
  docs: Array<Record<string, unknown>>;
  links: Array<Record<string, unknown>>;
}

export default function ProjectDetailPage() {
  const params = useParams();
  const name = decodeURIComponent(params.name as string);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .project(name)
      .then(setProject)
      .finally(() => setLoading(false));
  }, [name]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (!project) {
    return <p className="text-sm text-muted-foreground">Project not found.</p>;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-semibold">{project.name}</h1>

      {/* Documents */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Documents ({project.docs.length})
        </h2>
        {project.docs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents yet.</p>
        ) : (
          <div className="space-y-3">
            {project.docs.map((doc, i) => (
              <Card key={i}>
                <CardHeader className="p-4 pb-2">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium">
                      {(doc.doc_type as string) || "Document"}
                    </CardTitle>
                    {doc.doc_type ? (
                      <Badge variant="outline" className="text-xs">
                        {String(doc.doc_type)}
                      </Badge>
                    ) : null}
                  </div>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <p className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                    {(doc.content as string) || "—"}
                  </p>
                  {doc.created_at ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {new Date(doc.created_at as string).toLocaleDateString()}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Links */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Links ({project.links.length})
        </h2>
        {project.links.length === 0 ? (
          <p className="text-sm text-muted-foreground">No links.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {project.links.map((link, i) => (
              <Badge key={i} variant="secondary" className="gap-1">
                {(link.target as string) || "unknown"}
                <span className="text-muted-foreground">
                  ({(link.link_type as string) || "related"})
                </span>
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
