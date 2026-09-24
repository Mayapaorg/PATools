import { createFileRoute } from "@tanstack/react-router";
import { Desk } from "@/components/mail/desk";

export const Route = createFileRoute("/")({ component: Home });

function Home() {
  return <Desk />;
}
