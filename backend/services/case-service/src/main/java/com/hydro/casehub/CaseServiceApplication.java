package com.hydro.casehub;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.hydro.casehub.mapper")
public class CaseServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(CaseServiceApplication.class, args);
    }
}

