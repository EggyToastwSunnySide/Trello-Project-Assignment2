gitUSE TrelloDB;
DELIMITER //

DROP TRIGGER IF EXISTS TRIGGER_CHECK_CARD_LIMIT;

CREATE TRIGGER TRIGGER_CHECK_CARD_LIMIT
BEFORE INSERT ON Card
FOR EACH ROW
BEGIN
    DECLARE v_CardLimit INT;
    DECLARE v_CurrentCardCount INT;

    SELECT CardLimit INTO v_CardLimit
    FROM Lists WHERE ListID = NEW.ListID; 

    SELECT COUNT(*) INTO v_CurrentCardCount
    FROM Card WHERE ListID = NEW.ListID AND IsArchived = FALSE; 

    IF v_CardLimit > 0 AND v_CurrentCardCount >= v_CardLimit THEN
        SIGNAL SQLSTATE '45000' 
        SET MESSAGE_TEXT = 'ERROR: Cannot insert card. The List has reached its CardLimit.';
    END IF;
END //

DROP TRIGGER IF EXISTS TRIGGER_UPDATE_CARD_TIMESTAMP;

CREATE TRIGGER TRIGGER_UPDATE_CARD_TIMESTAMP
BEFORE UPDATE ON Card
FOR EACH ROW
BEGIN
    IF NEW.Title != OLD.Title 
       OR NEW.Description != OLD.Description 
       OR NEW.Priority != OLD.Priority 
       OR NEW.DueDate != OLD.DueDate 
       OR NEW.IsCompleted != OLD.IsCompleted THEN
       
       SET NEW.LastModified = NOW();
       
    END IF;
END //

DELIMITER ;