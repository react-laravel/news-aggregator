import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { isAdminRequest, unauthorized } from "@/lib/admin-auth";

const updateSchema = z.object({
  enabled: z.boolean().optional(),
  priority: z.number().int().min(1).optional(),
  name: z.string().min(1).optional(),
  baseUrl: z.string().url().nullable().optional().or(z.literal("")),
  query: z.string().nullable().optional(),
  categoryKeys: z.array(z.string()).optional(),
});

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  if (!(await isAdminRequest(request))) return unauthorized();
  const { id } = await params;
  const parsed = updateSchema.parse(await request.json());
  const source = await prisma.dataSource.update({
    where: { id },
    data: {
      ...parsed,
      baseUrl: parsed.baseUrl === "" ? null : parsed.baseUrl,
    },
  });
  return NextResponse.json({ source });
}

