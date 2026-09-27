package demo;
import java.util.List;
@SpringBootApplication class Main { @GetMapping("/x") public String run() { return "x"; } public static void main(String[] args) {} }