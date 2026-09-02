package com.clearflow.compliance.service;

import com.clearflow.compliance.domain.SDNEntry;
import com.opencsv.CSVReader;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.io.InputStreamReader;
import java.util.*;
import java.util.concurrent.locks.ReentrantReadWriteLock;

@Component
public class SDNLoader {
    private static final Logger log = LoggerFactory.getLogger(SDNLoader.class);

    private final ReentrantReadWriteLock lock = new ReentrantReadWriteLock();
    private List<SDNEntry> sdnEntries = new ArrayList<>();
    private List<String> allNames = new ArrayList<>();

    @PostConstruct
    public void loadSDN() {
        refreshSDN();
    }

    @Scheduled(fixedDelay = 86400000)
    public void refreshSDN() {
        lock.writeLock().lock();
        try {
            List<SDNEntry> loaded = new ArrayList<>();
            List<String> names = new ArrayList<>();
            try (CSVReader reader = new CSVReader(new InputStreamReader(new ClassPathResource("data/sdn_sample.csv").getInputStream()))) {
                String[] row;
                reader.readNext(); // skip header
                while ((row = reader.readNext()) != null) {
                    if (row.length < 5) continue;
                    String uid      = row[0].trim();
                    String name     = row[1].trim();
                    String type     = row[2].trim();
                    List<String> programs = Arrays.asList(row[3].split("\\|"));
                    String remarks  = row[4].trim();
                    List<String> variants = new ArrayList<>();
                    if (remarks.contains("AKA:")) {
                        String aka = remarks.substring(remarks.indexOf("AKA:") + 4).trim();
                        Arrays.stream(aka.split(";")).map(String::trim).filter(s -> !s.isBlank()).forEach(variants::add);
                    }
                    SDNEntry entry = new SDNEntry(uid, name, type, programs, remarks, variants, "UNKNOWN");
                    loaded.add(entry);
                    names.add(name);
                    names.addAll(variants);
                }
            } catch (Exception ex) {
                log.error("SDNLoader: failed to parse sdn_sample.csv — {}", ex.getMessage(), ex);
            }
            this.sdnEntries = loaded;
            this.allNames   = names;
            long individuals = loaded.stream().filter(e -> "Individual".equalsIgnoreCase(e.type())).count();
            long entities    = loaded.stream().filter(e -> "Entity".equalsIgnoreCase(e.type())).count();
            log.info("SDN list loaded: {} entries ({} individuals, {} entities), {} name variants total",
                    loaded.size(), individuals, entities, names.size());
        } finally {
            lock.writeLock().unlock();
        }
    }

    public List<String> getAllNames() {
        lock.readLock().lock();
        try {
            return List.copyOf(allNames);
        } finally {
            lock.readLock().unlock();
        }
    }
}
